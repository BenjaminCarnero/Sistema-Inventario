from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas, database, dependencies, auditoria

router = APIRouter(prefix="/descuentos", tags=["descuentos"])

# Crear/editar/borrar descuentos: sólo Admin y Encargado
gestor_descuentos = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)

TIPOS_VALIDOS = ("PORCENTAJE", "MONTO")


def _validar(descuento):
    if getattr(descuento, "tipo", None) is not None and descuento.tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail="tipo debe ser PORCENTAJE o MONTO")
    if getattr(descuento, "valor", None) is not None:
        if descuento.valor <= 0:
            raise HTTPException(status_code=400, detail="El valor debe ser mayor a 0")
        if descuento.tipo == "PORCENTAJE" and descuento.valor > 100:
            raise HTTPException(status_code=400, detail="Un porcentaje no puede superar 100")
    if descuento.fecha_inicio and descuento.fecha_fin and descuento.fecha_inicio > descuento.fecha_fin:
        raise HTTPException(status_code=400, detail="La fecha de inicio no puede ser posterior a la de fin")


@router.get("/", response_model=List[schemas.Descuento])
def read_descuentos(
    solo_vigentes: bool = False,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Lista descuentos. Con solo_vigentes=true devuelve los aplicables ahora
    (activos y dentro de su ventana de fechas), que es lo que consume el POS."""
    query = db.query(models.Descuento)
    if solo_vigentes:
        # En UTC, igual que las columnas contra las que se compara: con la
        # hora local del servidor un descuento se vencía a la hora equivocada.
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        query = query.filter(models.Descuento.activo == True)  # noqa: E712
        return [
            d for d in query.all()
            if (d.fecha_inicio is None or d.fecha_inicio <= ahora)
            and (d.fecha_fin is None or d.fecha_fin >= ahora)
        ]
    return query.order_by(models.Descuento.id.desc()).all()


@router.post("/", response_model=schemas.Descuento, status_code=status.HTTP_201_CREATED)
def create_descuento(
    descuento: schemas.DescuentoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_descuentos),
):
    _validar(descuento)

    if descuento.codigo_promocional:
        existe = db.query(models.Descuento).filter(
            models.Descuento.codigo_promocional == descuento.codigo_promocional
        ).first()
        if existe:
            raise HTTPException(status_code=400, detail="Ya existe un descuento con ese código promocional")

    if descuento.producto_id:
        producto = db.query(models.Producto).filter(models.Producto.id == descuento.producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

    nuevo = models.Descuento(**descuento.model_dump())
    db.add(nuevo)
    db.flush()

    auditoria.registrar(
        db, current_user, "descuento", "CREAR",
        entidad_id=nuevo.id, entidad_nombre=nuevo.nombre,
        campo="valor", valor_nuevo=f"{nuevo.valor} ({nuevo.tipo})",
    )

    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.put("/{descuento_id}", response_model=schemas.Descuento)
def update_descuento(
    descuento_id: int,
    descuento_update: schemas.DescuentoUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_descuentos),
):
    db_descuento = db.query(models.Descuento).filter(models.Descuento.id == descuento_id).first()
    if not db_descuento:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")

    cambios = descuento_update.model_dump(exclude_unset=True)

    # Validamos el estado resultante, no sólo los campos enviados: si sólo
    # cambia el valor de un descuento PORCENTAJE, igual hay que verificar <= 100.
    _validar(schemas.DescuentoBase(
        nombre=cambios.get("nombre", db_descuento.nombre),
        codigo_promocional=cambios.get("codigo_promocional", db_descuento.codigo_promocional),
        tipo=cambios.get("tipo", db_descuento.tipo),
        valor=cambios.get("valor", db_descuento.valor),
        producto_id=cambios.get("producto_id", db_descuento.producto_id),
        activo=cambios.get("activo", db_descuento.activo),
        fecha_inicio=cambios.get("fecha_inicio", db_descuento.fecha_inicio),
        fecha_fin=cambios.get("fecha_fin", db_descuento.fecha_fin),
    ))

    auditoria.registrar_cambios(
        db, current_user, "descuento", db_descuento, cambios,
        entidad_nombre=db_descuento.nombre,
    )

    for key, value in cambios.items():
        setattr(db_descuento, key, value)

    db.commit()
    db.refresh(db_descuento)
    return db_descuento


@router.delete("/{descuento_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_descuento(
    descuento_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_descuentos),
):
    db_descuento = db.query(models.Descuento).filter(models.Descuento.id == descuento_id).first()
    if not db_descuento:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")

    # Si ya se usó en alguna venta lo desactivamos en vez de borrarlo,
    # para no romper el historial de reportes.
    usado = db.query(models.Venta).filter(models.Venta.descuento_id == descuento_id).first()
    auditoria.registrar(
        db, current_user, "descuento", "ELIMINAR",
        entidad_id=db_descuento.id, entidad_nombre=db_descuento.nombre,
        valor_anterior=f"{db_descuento.valor} ({db_descuento.tipo})",
    )

    if usado:
        db_descuento.activo = False
        db.commit()
        return

    db.delete(db_descuento)
    db.commit()
