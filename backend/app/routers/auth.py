from datetime import timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app import models, schemas, auth, database, dependencies
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

get_admin_user = dependencies.require_role([models.RolEnum.ADMIN.value])

PIN_MINIMO = 4


@router.post("/login", response_model=schemas.Token)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
):
    ip = request.client.host if request.client else "desconocida"
    bloqueo = auth.segundos_de_bloqueo(form_data.username, ip)
    if bloqueo:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Probá de nuevo en {bloqueo} segundos.",
        )

    user = db.query(models.Usuario).filter(models.Usuario.nombre == form_data.username).first()

    if not user or not auth.verify_password(form_data.password, user.pin_acceso):
        auth.registrar_intento_fallido(form_data.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # Mensaje genérico a propósito: no revela si el usuario existe
            detail="Usuario o PIN incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Una cuenta dada de baja no debe poder iniciar sesión
    if not user.estado:
        auth.registrar_intento_fallido(form_data.username, ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )

    auth.limpiar_intentos(form_data.username, ip)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.nombre, "rol": user.rol_id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


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

    if len(user.pin_acceso or "") < PIN_MINIMO:
        raise HTTPException(
            status_code=400,
            detail=f"El PIN debe tener al menos {PIN_MINIMO} caracteres",
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

    db_user.nombre = nombre
    db_user.rol_id = user_update.rol_id
    db_user.estado = user_update.estado
    db.commit()
    db.refresh(db_user)
    return db_user


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

    # Baja lógica: las ventas pasadas siguen refiriendo a este usuario
    db_user.estado = False
    db.commit()
    return
