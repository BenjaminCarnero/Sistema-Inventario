from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas, database, dependencies

router = APIRouter(prefix="/stock", tags=["stock"])

# Mover stock cambia el inventario y la rentabilidad: no es tarea del cajero.
gestor_stock = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)

TIPOS_PERMITIDOS = (
    models.TipoMovimientoEnum.INGRESO.value,
    models.TipoMovimientoEnum.AJUSTE.value,
)


@router.post("/movimientos", response_model=schemas.MovimientoStockOut, status_code=status.HTTP_201_CREATED)
def registrar_movimiento(
    payload: schemas.MovimientoStockCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_stock),
):
    """Carga mercadería o corrige el stock, dejando registro de quién y por qué.

    - INGRESO: llegó mercadería. La cantidad se SUMA al stock.
    - AJUSTE: recuento físico. La cantidad es el stock REAL contado, y se
      guarda la diferencia contra lo que decía el sistema.

    Hasta ahora el stock sólo bajaba con las ventas: la única forma de subirlo
    era editar el producto a mano, sin dejar rastro de nada.
    """
    if payload.tipo_movimiento not in TIPOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"El tipo debe ser {' o '.join(TIPOS_PERMITIDOS)}. Las salidas las genera la venta.",
        )

    producto = db.query(models.Producto).filter(
        models.Producto.id == payload.producto_id
    ).with_for_update().first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    anterior = producto.stock_actual or 0

    if payload.tipo_movimiento == models.TipoMovimientoEnum.INGRESO.value:
        producto.stock_actual = anterior + payload.cantidad
        cantidad_registrada = payload.cantidad
        motivo = (payload.motivo or "").strip() or "Ingreso de mercadería"
    else:
        # En un ajuste la cantidad es el conteo físico, no la diferencia
        diferencia = payload.cantidad - anterior
        producto.stock_actual = payload.cantidad
        cantidad_registrada = abs(diferencia)
        detalle = f"Ajuste por recuento: {anterior} → {payload.cantidad}"
        motivo = f"{(payload.motivo or '').strip()} ({detalle})".strip() if payload.motivo else detalle

    movimiento = models.MovimientoStock(
        producto_id=producto.id,
        usuario_id=current_user.id,
        tipo_movimiento=payload.tipo_movimiento,
        cantidad=cantidad_registrada,
        motivo=motivo[:255],
    )
    db.add(movimiento)
    db.commit()
    db.refresh(movimiento)

    return schemas.MovimientoStockOut(
        id=movimiento.id,
        producto_id=movimiento.producto_id,
        usuario_id=movimiento.usuario_id,
        tipo_movimiento=movimiento.tipo_movimiento,
        cantidad=movimiento.cantidad,
        fecha_hora=movimiento.fecha_hora,
        motivo=movimiento.motivo,
        producto_nombre=producto.nombre,
        usuario_nombre=current_user.nombre,
    )


@router.get("/movimientos", response_model=List[schemas.MovimientoStockOut])
def historial_movimientos(
    producto_id: Optional[int] = Query(None, description="Filtrar por producto"),
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_stock),
):
    """Historial de entradas, salidas y ajustes. Sirve para auditar el stock."""
    query = db.query(models.MovimientoStock)
    if producto_id:
        query = query.filter(models.MovimientoStock.producto_id == producto_id)

    movimientos = query.order_by(models.MovimientoStock.id.desc()).limit(limite).all()

    productos = {p.id: p.nombre for p in db.query(models.Producto).all()}
    usuarios = {u.id: u.nombre for u in db.query(models.Usuario).all()}

    return [
        schemas.MovimientoStockOut(
            id=m.id,
            producto_id=m.producto_id,
            usuario_id=m.usuario_id,
            tipo_movimiento=m.tipo_movimiento,
            cantidad=m.cantidad,
            fecha_hora=m.fecha_hora,
            motivo=m.motivo,
            producto_nombre=productos.get(m.producto_id, "Producto eliminado"),
            usuario_nombre=usuarios.get(m.usuario_id, "Desconocido"),
        )
        for m in movimientos
    ]
