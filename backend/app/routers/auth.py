from datetime import timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app import models, schemas, auth, database, dependencies, auditoria, red
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

get_admin_user = dependencies.require_role([models.RolEnum.ADMIN.value])

# La política de largo mínimo vive en `app/auth.py`, que es lo que también usa
# el script de instalación: tenerla acá dejaba crear el primer administrador
# con un PIN de cuatro caracteres.
_pin_minimo = auth.pin_minimo


@router.post("/login", response_model=schemas.Token)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
):
    ip = red.ip_del_cliente(request)
    bloqueo = auth.segundos_de_bloqueo(db, form_data.username, ip)
    if bloqueo:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Probá de nuevo en {bloqueo} segundos.",
        )

    user = db.query(models.Usuario).filter(models.Usuario.nombre == form_data.username).first()

    # Se verifica siempre, exista la cuenta o no, para que el tiempo de
    # respuesta no delate qué nombres de usuario son válidos.
    if not auth.verificar_credencial(form_data.password, user.pin_acceso if user else None):
        auth.registrar_intento_fallido(db, form_data.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # Mensaje genérico a propósito: no revela si el usuario existe
            detail="Usuario o PIN incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Una cuenta dada de baja no debe poder iniciar sesión
    if not user.estado:
        auth.registrar_intento_fallido(db, form_data.username, ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )

    auth.limpiar_intentos(db, form_data.username, ip)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # El `sub` es el id y no el nombre: el nombre se puede reasignar a otra
    # cuenta y eso convertía una sesión de cajero en una de administrador.
    # `cv` es la versión de credencial, para poder revocar la sesión al
    # cambiar el PIN.
    access_token = auth.create_access_token(
        data={
            "sub": str(user.id),
            "rol": user.rol_id,
            "cv": user.credenciales_version or 1,
            # Sólo para que la pantalla muestre quién está adentro. La
            # identidad la da `sub`: de este campo el servidor no lee nada.
            "nombre": user.nombre,
        },
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/estado-inicial")
def estado_inicial(db: Session = Depends(database.get_db)):
    """Si la base todavía no tiene usuarios, el frontend ofrece el asistente
    de primer arranque en vez del formulario de acceso. No requiere sesión:
    no revela nada que no se sepa mirando la pantalla de login (¿hay o no hay
    con quién entrar?), y es justo lo que hace falta saber antes de poder
    entrar con alguien.
    """
    hay_usuarios = db.query(models.Usuario).first() is not None
    return {"hay_usuarios": hay_usuarios}


@router.post("/register", response_model=schemas.Usuario, status_code=status.HTTP_201_CREATED)
def register_user(
    user: schemas.UsuarioCreate,
    db: Session = Depends(database.get_db),
    token: Optional[str] = Depends(dependencies.oauth2_scheme_opcional),
):
    """Alta de usuarios. Sólo un administrador puede crear cuentas.

    Se permite una única excepción: si la base todavía no tiene ningún usuario,
    se acepta el primer alta sin token para poder inicializar el sistema. En
    cuanto existe un usuario, el endpoint queda cerrado.
    """
    hay_usuarios = db.query(models.Usuario).first() is not None

    if hay_usuarios:
        # Se resuelve el usuario a mano porque este endpoint acepta token opcional
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Se necesita iniciar sesión como administrador para crear usuarios",
                headers={"WWW-Authenticate": "Bearer"},
            )
        actual = dependencies.get_current_user(token=token, db=db)
        if not actual.estado or actual.rol_id != models.RolEnum.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sólo un administrador puede crear usuarios",
            )

    nombre = (user.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre de usuario no puede estar vacío")

    minimo = _pin_minimo(user.rol_id)
    if len(user.pin_acceso or "") < minimo:
        raise HTTPException(
            status_code=400,
            detail=f"El PIN debe tener al menos {minimo} caracteres para este rol",
        )

    if user.rol_id not in (r.value for r in models.RolEnum):
        raise HTTPException(status_code=400, detail="Rol inválido")

    db_user = db.query(models.Usuario).filter(models.Usuario.nombre == nombre).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Ese nombre de usuario ya existe")

    hashed_password = auth.get_password_hash(user.pin_acceso)
    db_user = models.Usuario(
        nombre=nombre,
        pin_acceso=hashed_password,
        rol_id=user.rol_id,
        estado=user.estado,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/users", response_model=List[schemas.Usuario])
def get_users(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(get_admin_user)):
    return db.query(models.Usuario).all()


def _quedan_otros_admins(db: Session, excepto_id: int) -> bool:
    """¿Hay algún otro administrador activo además del indicado?"""
    return db.query(models.Usuario).filter(
        models.Usuario.rol_id == models.RolEnum.ADMIN.value,
        models.Usuario.estado == True,  # noqa: E712
        models.Usuario.id != excepto_id,
    ).first() is not None


@router.put("/users/{user_id}", response_model=schemas.Usuario)
def update_user(
    user_id: int,
    user_update: schemas.UsuarioBase,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_admin_user),
):
    db_user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    nombre = (user_update.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre de usuario no puede estar vacío")

    if user_update.rol_id not in (r.value for r in models.RolEnum):
        raise HTTPException(status_code=400, detail="Rol inválido")

    # Nadie puede dejar al sistema sin ningún administrador activo
    era_admin_activo = db_user.rol_id == models.RolEnum.ADMIN.value and db_user.estado
    deja_de_ser_admin = user_update.rol_id != models.RolEnum.ADMIN.value or not user_update.estado
    if era_admin_activo and deja_de_ser_admin and not _quedan_otros_admins(db, db_user.id):
        raise HTTPException(
            status_code=400,
            detail="No podés quitar al último administrador: el sistema quedaría sin acceso.",
        )

    # El nombre nuevo no puede chocar con otro usuario
    repetido = db.query(models.Usuario).filter(
        models.Usuario.nombre == nombre, models.Usuario.id != user_id
    ).first()
    if repetido:
        raise HTTPException(status_code=400, detail="Ese nombre de usuario ya existe")

    auditoria.registrar_cambios(
        db, current_user, "usuario", db_user,
        {"rol_id": user_update.rol_id, "estado": user_update.estado},
        entidad_nombre=db_user.nombre,
    )

    db_user.nombre = nombre
    db_user.rol_id = user_update.rol_id
    db_user.estado = user_update.estado
    db.commit()
    db.refresh(db_user)
    return db_user


@router.put("/me/pin", status_code=status.HTTP_204_NO_CONTENT)
def cambiar_mi_pin(
    cambio: schemas.CambioDePinPropio,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Cambio del PIN propio.

    Sin esto, un PIN visto por encima del hombro sólo se podía sacar de
    circulación borrando la cuenta y creándola de nuevo, lo que le cambia el id
    y desengancha del historial las ventas de esa persona.
    """
    ip = red.ip_del_cliente(request)

    # El PIN actual se pide para que un equipo dejado abierto no alcance para
    # quedarse con la cuenta. Cuenta como intento fallido, así el mismo freno
    # que protege al login protege también a este endpoint.
    bloqueo = auth.segundos_de_bloqueo(db, current_user.nombre, ip)
    if bloqueo:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Probá de nuevo en {bloqueo} segundos.",
        )

    if not auth.verificar_credencial(cambio.pin_actual, current_user.pin_acceso):
        auth.registrar_intento_fallido(db, current_user.nombre, ip)
        raise HTTPException(status_code=400, detail="El PIN actual no es correcto")

    minimo = _pin_minimo(current_user.rol_id)
    if len(cambio.pin_nuevo or "") < minimo:
        raise HTTPException(
            status_code=400,
            detail=f"El PIN debe tener al menos {minimo} caracteres para este rol",
        )
    if cambio.pin_nuevo == cambio.pin_actual:
        raise HTTPException(status_code=400, detail="El PIN nuevo tiene que ser distinto del actual")

    auth.limpiar_intentos(db, current_user.nombre, ip)
    current_user.pin_acceso = auth.get_password_hash(cambio.pin_nuevo)
    # Corta todas las sesiones abiertas con el PIN viejo, incluida la que está
    # haciendo este pedido: quien cambia su PIN porque se lo vieron necesita
    # que el que lo vio quede afuera ya, no dentro de doce horas.
    current_user.credenciales_version = (current_user.credenciales_version or 1) + 1

    # Queda el registro de que se cambió, nunca el PIN en sí
    auditoria.registrar(
        db, current_user, "usuario", "MODIFICAR",
        entidad_id=current_user.id, entidad_nombre=current_user.nombre,
        campo="pin_acceso", valor_anterior="(oculto)", valor_nuevo="(cambiado por el propio usuario)",
    )
    db.commit()
    return


@router.put("/users/{user_id}/pin", status_code=status.HTTP_204_NO_CONTENT)
def reiniciar_pin(
    user_id: int,
    cambio: schemas.ReinicioDePin,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_admin_user),
):
    """Reinicio del PIN de otra cuenta: para el cajero que se lo olvidó."""
    db_user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    minimo = _pin_minimo(db_user.rol_id)
    if len(cambio.pin_nuevo or "") < minimo:
        raise HTTPException(
            status_code=400,
            detail=f"El PIN debe tener al menos {minimo} caracteres para este rol",
        )

    db_user.pin_acceso = auth.get_password_hash(cambio.pin_nuevo)
    # Reiniciar el PIN de una cuenta comprometida tiene que cerrarla de verdad.
    # Antes el administrador creía haberla cerrado y no la cerraba: el token
    # que tuviera el atacante seguía valiendo.
    db_user.credenciales_version = (db_user.credenciales_version or 1) + 1

    # Un PIN reiniciado por otro deja bloqueada a la cuenta si arrastraba
    # fallos, así que se limpian junto con el cambio.
    auth.limpiar_intentos_de_cuenta(db, db_user.nombre)

    auditoria.registrar(
        db, current_user, "usuario", "MODIFICAR",
        entidad_id=db_user.id, entidad_nombre=db_user.nombre,
        campo="pin_acceso", valor_anterior="(oculto)", valor_nuevo="(reiniciado por un administrador)",
    )
    db.commit()
    return


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_admin_user),
):
    db_user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if db_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="No podés eliminar tu propia cuenta")

    if db_user.rol_id == models.RolEnum.ADMIN.value and db_user.estado and not _quedan_otros_admins(db, db_user.id):
        raise HTTPException(
            status_code=400,
            detail="No podés eliminar al último administrador: el sistema quedaría sin acceso.",
        )

    auditoria.registrar(
        db, current_user, "usuario", "ELIMINAR",
        entidad_id=db_user.id, entidad_nombre=db_user.nombre,
        campo="estado", valor_anterior=db_user.estado, valor_nuevo=False,
    )

    # Baja lógica: las ventas pasadas siguen refiriendo a este usuario
    db_user.estado = False
    db.commit()
    return
