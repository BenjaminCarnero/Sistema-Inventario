from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models, schemas, database, dependencies
from app.fechas import filtro_de_dias

router = APIRouter(prefix="/auditoria", tags=["auditoria"])

# El registro muestra quién tocó qué. Que lo lea sólo el administrador: un
# encargado no debería poder revisar si lo están controlando.
solo_admin = dependencies.require_role([models.RolEnum.ADMIN.value])


@router.get("/", response_model=List[schemas.EntradaAuditoria])
def listar_auditoria(
    entidad: Optional[str] = Query(None, description="producto, descuento, configuracion o usuario"),
    usuario_id: Optional[int] = Query(None),
    desde: Optional[str] = Query(None, description="YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limite: int = Query(200, ge=1, le=2000),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(solo_admin),
):
    query = db.query(models.Auditoria)

    if entidad:
        query = query.filter(models.Auditoria.entidad == entidad)
    if usuario_id:
        query = query.filter(models.Auditoria.usuario_id == usuario_id)
    # Días del calendario del local convertidos a UTC, que es como se guardan.
    # El rango incluye el día final entero.
    inicio, fin = filtro_de_dias(desde, hasta)
    if inicio is not None:
        query = query.filter(models.Auditoria.fecha_hora >= inicio)
    if fin is not None:
        query = query.filter(models.Auditoria.fecha_hora < fin)

    entradas = query.order_by(models.Auditoria.id.desc()).limit(limite).all()

    nombres = {u.id: u.nombre for u in db.query(models.Usuario).all()}

    return [
        schemas.EntradaAuditoria(
            id=e.id,
            usuario_id=e.usuario_id,
            usuario_nombre=nombres.get(e.usuario_id, "Sistema"),
            fecha_hora=e.fecha_hora,
            entidad=e.entidad,
            entidad_id=e.entidad_id,
            entidad_nombre=e.entidad_nombre,
            accion=e.accion,
            campo=e.campo,
            valor_anterior=e.valor_anterior,
            valor_nuevo=e.valor_nuevo,
        )
        for e in entradas
    ]
