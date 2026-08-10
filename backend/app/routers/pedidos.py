from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas, database, dependencies
from app.models import ahora_utc
from app.routers.configuracion import obtener_config

router = APIRouter(prefix="/pedidos", tags=["pedidos"])

# Pedir mercadería compromete plata del negocio: no es tarea del cajero.
gestor_pedidos = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)


def _en_camino(db: Session) -> dict[int, int]:
    """Unidades de cada producto que ya están pedidas y todavía no llegaron.

    Es el dato que evita pedir dos veces lo mismo, que es justo lo que pasa
    cuando el pedido vive sólo en el historial de WhatsApp.
    """
    filas = db.query(
        models.DetallePedido.producto_id,
        func.sum(models.DetallePedido.cantidad),
    ).join(
        models.Pedido, models.Pedido.id == models.DetallePedido.pedido_id
    ).filter(
        models.Pedido.estado == models.EstadoPedidoEnum.PENDIENTE.value
    ).group_by(models.DetallePedido.producto_id).all()

    return {producto_id: int(total or 0) for producto_id, total in filas}


@router.get("/reponer", response_model=List[schemas.GrupoAReponer])
def sugerencia_de_reposicion(
    umbral: Optional[int] = Query(None, ge=0, description="Por defecto, el configurado en el sistema"),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_pedidos),
):
    """Lo que falta reponer, agrupado por proveedor.

    Se agrupa por proveedor porque el pedido se hace por proveedor, no por
    producto. Los que no tienen proveedor asignado no se esconden: van en su
    propio grupo, para que la pantalla sirva desde el primer día aunque no se
    haya cargado todavía ninguna ficha.
    """
    if umbral is None:
        umbral = int(obtener_config(db).get("umbral_stock_bajo") or 5)

    productos = db.query(models.Producto).filter(
        models.Producto.stock_actual < umbral
    ).order_by(models.Producto.stock_actual.asc()).all()

    en_camino = _en_camino(db)
    proveedores = {p.id: p for p in db.query(models.Proveedor).all()}

    # None agrupa a los que no tienen proveedor todavía
    grupos: dict[Optional[int], List[schemas.ItemAReponer]] = {}
    for producto in productos:
        grupos.setdefault(producto.proveedor_id, []).append(schemas.ItemAReponer(
            producto_id=producto.id,
            producto_nombre=producto.nombre,
            codigo_barras=producto.codigo_barras,
            stock_actual=producto.stock_actual or 0,
            cantidad_sugerida=producto.cantidad_pedido_habitual,
            ya_pedido=en_camino.get(producto.id, 0),
        ))

    resultado = []
    for proveedor_id, items in grupos.items():
        proveedor = proveedores.get(proveedor_id) if proveedor_id else None
        resultado.append(schemas.GrupoAReponer(
            proveedor_id=proveedor_id,
            proveedor_nombre=proveedor.nombre if proveedor else None,
            proveedor_telefono=proveedor.telefono if proveedor else None,
            items=items,
        ))

    # Los que no tienen proveedor van al final: son los que hay que completar,
    # no los que se van a pedir ahora.
    resultado.sort(key=lambda g: (g.proveedor_id is None, (g.proveedor_nombre or "").lower()))
    return resultado


def _armar_respuesta(db: Session, pedido: models.Pedido) -> schemas.Pedido:
    proveedor = db.query(models.Proveedor).filter(
        models.Proveedor.id == pedido.proveedor_id
    ).first()
    usuario = db.query(models.Usuario).filter(models.Usuario.id == pedido.usuario_id).first()

    nombres = {
        p.id: p.nombre
        for p in db.query(models.Producto).filter(
            models.Producto.id.in_([d.producto_id for d in pedido.detalles] or [0])
        )
    }

    return schemas.Pedido(
        id=pedido.id,
        proveedor_id=pedido.proveedor_id,
        proveedor_nombre=proveedor.nombre if proveedor else None,
        proveedor_telefono=proveedor.telefono if proveedor else None,
        usuario_id=pedido.usuario_id,
        usuario_nombre=usuario.nombre if usuario else None,
        fecha_hora=pedido.fecha_hora,
        estado=pedido.estado,
        fecha_recepcion=pedido.fecha_recepcion,
        notas=pedido.notas,
        detalles=[
            schemas.DetallePedido(
                id=d.id,
                producto_id=d.producto_id,
                producto_nombre=nombres.get(d.producto_id, "Producto eliminado"),
                cantidad=d.cantidad,
                cantidad_recibida=d.cantidad_recibida,
            )
            for d in pedido.detalles
        ],
    )


@router.get("/", response_model=List[schemas.Pedido])
def listar_pedidos(
    estado: Optional[str] = Query(None, description="PENDIENTE, RECIBIDO o CANCELADO"),
    limite: int = Query(50, ge=1, le=500),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_pedidos),
):
    query = db.query(models.Pedido)

    if estado:
        estado = estado.upper()
        if estado not in {e.value for e in models.EstadoPedidoEnum}:
            raise HTTPException(status_code=400, detail="Estado de pedido desconocido")
        query = query.filter(models.Pedido.estado == estado)

    pedidos = query.order_by(models.Pedido.id.desc()).limit(limite).all()
    return [_armar_respuesta(db, p) for p in pedidos]


@router.get("/{pedido_id}", response_model=schemas.Pedido)
def ver_pedido(
    pedido_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_pedidos),
):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return _armar_respuesta(db, pedido)


@router.post("/", response_model=schemas.Pedido, status_code=status.HTTP_201_CREATED)
def crear_pedido(
    payload: schemas.PedidoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_pedidos),
):
    """Registra un pedido a un proveedor. No toca el stock: todavía no llegó."""
    proveedor = db.query(models.Proveedor).filter(
        models.Proveedor.id == payload.proveedor_id
    ).first()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    if not payload.detalles:
        raise HTTPException(status_code=400, detail="El pedido no tiene ningún producto")

    # Un mismo producto puede venir repetido desde la pantalla: se suma
    pedidas: dict[int, int] = {}
    for detalle in payload.detalles:
        pedidas[detalle.producto_id] = pedidas.get(detalle.producto_id, 0) + detalle.cantidad

    existentes = {
        p.id for p in db.query(models.Producto.id).filter(models.Producto.id.in_(pedidas))
    }
    faltantes = set(pedidas) - existentes
    if faltantes:
        raise HTTPException(
            status_code=404,
            detail=f"No existe el producto {sorted(faltantes)[0]}",
        )

    pedido = models.Pedido(
        proveedor_id=proveedor.id,
        usuario_id=current_user.id,
        estado=models.EstadoPedidoEnum.PENDIENTE.value,
        notas=(payload.notas or "").strip() or None,
    )
    db.add(pedido)
    db.flush()

    for producto_id, cantidad in pedidas.items():
        db.add(models.DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto_id,
            cantidad=cantidad,
        ))

    db.commit()
    db.refresh(pedido)
    return _armar_respuesta(db, pedido)


@router.post("/{pedido_id}/recibir", response_model=schemas.Pedido)
def recibir_pedido(
    pedido_id: int,
    payload: schemas.PedidoRecibir,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_pedidos),
):
    """Llegó la mercadería: carga todo el stock de una.

    Sin `detalles` se da por recibido lo que se había pedido. Con `detalles` se
    puede corregir producto por producto, porque el proveedor manda lo que
    tiene y casi nunca coincide exactamente con lo pedido.
    """
    try:
        pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if pedido.estado != models.EstadoPedidoEnum.PENDIENTE.value:
            raise HTTPException(
                status_code=400,
                detail=f"El pedido ya está {pedido.estado.lower()}",
            )

        correcciones = {d.producto_id: d.cantidad_recibida for d in payload.detalles}
        del_pedido = {d.producto_id for d in pedido.detalles}
        ajenos = set(correcciones) - del_pedido
        if ajenos:
            raise HTTPException(
                status_code=400,
                detail=f"El producto {sorted(ajenos)[0]} no forma parte de este pedido",
            )

        proveedor = db.query(models.Proveedor).filter(
            models.Proveedor.id == pedido.proveedor_id
        ).first()
        motivo = f"Pedido #{pedido.id}" + (f" a {proveedor.nombre}" if proveedor else "")

        for detalle in pedido.detalles:
            recibida = correcciones.get(detalle.producto_id, detalle.cantidad)
            detalle.cantidad_recibida = recibida
            if recibida <= 0:
                continue  # no vino nada de este producto

            producto = db.query(models.Producto).filter(
                models.Producto.id == detalle.producto_id
            ).with_for_update().first()
            if producto:
                producto.stock_actual = (producto.stock_actual or 0) + recibida

            db.add(models.MovimientoStock(
                producto_id=detalle.producto_id,
                usuario_id=current_user.id,
                tipo_movimiento=models.TipoMovimientoEnum.INGRESO.value,
                cantidad=recibida,
                motivo=motivo[:255],
            ))

        pedido.estado = models.EstadoPedidoEnum.RECIBIDO.value
        pedido.fecha_recepcion = ahora_utc()

        db.commit()
        db.refresh(pedido)
        return _armar_respuesta(db, pedido)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{pedido_id}/cancelar", response_model=schemas.Pedido)
def cancelar_pedido(
    pedido_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_pedidos),
):
    """El pedido no va a llegar. No toca el stock: nunca lo había tocado."""
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if pedido.estado == models.EstadoPedidoEnum.RECIBIDO.value:
        raise HTTPException(
            status_code=400,
            detail="El pedido ya se recibió: la mercadería está en el stock",
        )

    pedido.estado = models.EstadoPedidoEnum.CANCELADO.value
    db.commit()
    db.refresh(pedido)
    return _armar_respuesta(db, pedido)
