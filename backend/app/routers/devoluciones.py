import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, database, dependencies, auditoria
from app.routers.configuracion import obtener_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devoluciones", tags=["devoluciones"])

# Devolver plata mueve la caja: no es tarea de un cajero cualquiera.
gestor_devoluciones = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)

METODOS_VALIDOS = {m.value for m in models.MetodoPagoEnum} | {"MERCADOPAGO"}


def _caja_de_la_que_sale(db: Session, usuario: models.Usuario) -> int | None:
    """De qué turno de caja sale la plata de esta devolución.

    Las devoluciones las autoriza un encargado, que muchas veces no tiene caja
    propia abierta: la plata sale igual del cajón que está funcionando. Por eso
    se busca primero la caja del que la registra y, si no tiene, la única que
    esté abierta.

    Con varias cajas abiertas y sin una propia no hay forma de adivinar cuál
    es, así que queda en None y el arqueo vuelve a contarla por ventana de
    tiempo, como se hacía antes.
    """
    propia = db.query(models.CajaTurno).filter(
        models.CajaTurno.usuario_id == usuario.id,
        models.CajaTurno.fecha_cierre == None,  # noqa: E711
    ).first()
    if propia:
        return propia.id

    abiertas = db.query(models.CajaTurno).filter(
        models.CajaTurno.fecha_cierre == None,  # noqa: E711
    ).limit(2).all()
    return abiertas[0].id if len(abiertas) == 1 else None


def _devuelto_por_producto(db: Session, venta_id: int) -> dict[int, int]:
    """Cuántas unidades de cada producto ya se devolvieron de esta venta."""
    filas = db.query(
        models.DetalleDevolucion.producto_id,
        models.DetalleDevolucion.cantidad,
    ).join(
        models.Devolucion, models.Devolucion.id == models.DetalleDevolucion.devolucion_id
    ).filter(models.Devolucion.venta_id == venta_id).all()

    acumulado: dict[int, int] = {}
    for producto_id, cantidad in filas:
        acumulado[producto_id] = acumulado.get(producto_id, 0) + cantidad
    return acumulado


@router.get("/venta/{venta_id}/disponible", response_model=List[schemas.ProductoDevolvible])
def productos_devolvibles(
    venta_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_devoluciones),
):
    """Qué se puede devolver todavía de una venta.

    Sirve para que la pantalla no ofrezca devolver más de lo que se vendió.
    """
    venta = db.query(models.Venta).filter(models.Venta.id == venta_id).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    ya_devuelto = _devuelto_por_producto(db, venta_id)

    # Una venta puede tener el mismo producto en varias líneas: se agrupan
    vendido: dict[int, dict] = {}
    for d in venta.detalles:
        item = vendido.setdefault(d.producto_id, {"cantidad": 0, "precio": d.precio_unitario})
        item["cantidad"] += d.cantidad

    resultado = []
    for producto_id, info in vendido.items():
        producto = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
        devuelta = ya_devuelto.get(producto_id, 0)
        resultado.append(schemas.ProductoDevolvible(
            producto_id=producto_id,
            producto_nombre=producto.nombre if producto else "Producto eliminado",
            precio_unitario=info["precio"],
            cantidad_vendida=info["cantidad"],
            cantidad_devuelta=devuelta,
            cantidad_disponible=max(0, info["cantidad"] - devuelta),
        ))
    return resultado


@router.get("/venta/{venta_id}", response_model=List[schemas.Devolucion])
def devoluciones_de_venta(
    venta_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_devoluciones),
):
    devoluciones = db.query(models.Devolucion).filter(
        models.Devolucion.venta_id == venta_id
    ).order_by(models.Devolucion.id.desc()).all()

    return [_armar_respuesta(db, d) for d in devoluciones]


def _armar_respuesta(db: Session, devolucion: models.Devolucion) -> schemas.Devolucion:
    usuario = db.query(models.Usuario).filter(models.Usuario.id == devolucion.usuario_id).first()
    detalles = []
    for d in devolucion.detalles:
        producto = db.query(models.Producto).filter(models.Producto.id == d.producto_id).first()
        detalles.append(schemas.DetalleDevolucion(
            id=d.id,
            producto_id=d.producto_id,
            cantidad=d.cantidad,
            precio_unitario=d.precio_unitario,
            subtotal=d.subtotal,
            producto_nombre=producto.nombre if producto else "Producto eliminado",
        ))
    return schemas.Devolucion(
        id=devolucion.id,
        venta_id=devolucion.venta_id,
        usuario_id=devolucion.usuario_id,
        fecha_hora=devolucion.fecha_hora,
        motivo=devolucion.motivo,
        total_devuelto=devolucion.total_devuelto,
        es_anulacion=devolucion.es_anulacion,
        metodo_devolucion=devolucion.metodo_devolucion,
        usuario_nombre=usuario.nombre if usuario else None,
        detalles=detalles,
    )


@router.post("/venta/{venta_id}", response_model=schemas.Devolucion, status_code=status.HTTP_201_CREATED)
def crear_devolucion(
    venta_id: int,
    payload: schemas.DevolucionCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_devoluciones),
):
    """Devuelve productos de una venta y repone el stock.

    Sin `detalles` se devuelve todo lo que quede pendiente, que es lo que se
    usa para anular una venta entera.
    """
    try:
        venta = db.query(models.Venta).filter(models.Venta.id == venta_id).first()
        if not venta:
            raise HTTPException(status_code=404, detail="Venta no encontrada")

        if venta.estado == models.EstadoVentaEnum.ANULADA.value:
            raise HTTPException(status_code=400, detail="La venta ya está anulada")

        if payload.metodo_devolucion not in METODOS_VALIDOS:
            raise HTTPException(
                status_code=400,
                detail=f"Método de devolución inválido. Válidos: {', '.join(sorted(METODOS_VALIDOS))}"
            )

        ya_devuelto = _devuelto_por_producto(db, venta_id)

        # Lo vendido, agrupado por producto (una venta puede repetir producto)
        vendido: dict[int, dict] = {}
        for d in venta.detalles:
            item = vendido.setdefault(d.producto_id, {"cantidad": 0, "precio": d.precio_unitario})
            item["cantidad"] += d.cantidad

        # Sin detalles explícitos se devuelve todo el saldo pendiente
        if payload.detalles:
            pedido = [(d.producto_id, d.cantidad) for d in payload.detalles]
        else:
            pedido = [
                (pid, info["cantidad"] - ya_devuelto.get(pid, 0))
                for pid, info in vendido.items()
                if info["cantidad"] - ya_devuelto.get(pid, 0) > 0
            ]

        if not pedido:
            raise HTTPException(status_code=400, detail="No queda nada por devolver en esta venta")

        # Validar antes de tocar nada
        for producto_id, cantidad in pedido:
            if producto_id not in vendido:
                raise HTTPException(
                    status_code=400,
                    detail=f"El producto {producto_id} no forma parte de esta venta"
                )
            disponible = vendido[producto_id]["cantidad"] - ya_devuelto.get(producto_id, 0)
            if cantidad > disponible:
                nombre = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No se puede devolver {cantidad} de "
                        f"'{nombre.nombre if nombre else producto_id}': quedan {disponible}"
                    ),
                )

        # La proporción del total que representa lo devuelto. Se calcula sobre
        # el total real cobrado, así el descuento y el IVA quedan repartidos.
        bruto_venta = sum(d.cantidad * d.precio_unitario for d in venta.detalles) or 1
        factor = venta.total / bruto_venta

        # Devolver es sacar plata de la caja. Por encima del tope hace falta un
        # administrador: el encargado resuelve el día a día, pero una
        # devolución grande deja de ser una decisión de mostrador.
        #
        # Se verifica antes de tocar el stock. Podría confiarse en que el
        # rollback deshaga lo hecho, pero rechazar algo después de haberlo
        # aplicado a medias es la clase de código que un día falla mal.
        a_devolver = round(sum(
            round(cantidad * vendido[producto_id]["precio"] * factor, 2)
            for producto_id, cantidad in pedido
        ), 2)

        tope = float(obtener_config(db).get("devolucion_tope_encargado") or 0)
        if tope > 0 and current_user.rol_id != models.RolEnum.ADMIN.value and a_devolver > tope:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Una devolución de {a_devolver:.2f} supera el tope de {tope:.2f} "
                    "para tu rol. La tiene que hacer un administrador."
                ),
            )

        devolucion = models.Devolucion(
            venta_id=venta.id,
            usuario_id=current_user.id,
            motivo=(payload.motivo or "").strip() or None,
            total_devuelto=0,
            es_anulacion=not payload.detalles,
            metodo_devolucion=payload.metodo_devolucion,
            caja_turno_id=_caja_de_la_que_sale(db, current_user),
        )
        db.add(devolucion)
        db.flush()

        total_devuelto = 0.0
        for producto_id, cantidad in pedido:
            precio = vendido[producto_id]["precio"]
            subtotal = round(cantidad * precio * factor, 2)
            total_devuelto += subtotal

            db.add(models.DetalleDevolucion(
                devolucion_id=devolucion.id,
                producto_id=producto_id,
                cantidad=cantidad,
                precio_unitario=precio,
                subtotal=subtotal,
            ))

            # La mercadería vuelve al depósito
            producto = db.query(models.Producto).filter(
                models.Producto.id == producto_id
            ).with_for_update().first()
            if producto:
                producto.stock_actual += cantidad

            db.add(models.MovimientoStock(
                producto_id=producto_id,
                usuario_id=current_user.id,
                tipo_movimiento=models.TipoMovimientoEnum.INGRESO.value,
                cantidad=cantidad,
                motivo=f"Devolución de venta #{venta.id}",
            ))

        devolucion.total_devuelto = round(total_devuelto, 2)

        auditoria.registrar(
            db, current_user, "devolucion", "CREAR",
            entidad_id=devolucion.id, entidad_nombre=f"Venta #{venta.id}",
            campo="total_devuelto", valor_nuevo=devolucion.total_devuelto,
        )

        # Estado de la venta: anulada si ya no queda nada, parcial si queda algo
        devuelto_final = _devuelto_por_producto(db, venta_id)
        for producto_id, cantidad in pedido:
            devuelto_final[producto_id] = devuelto_final.get(producto_id, 0) + cantidad

        queda_algo = any(
            info["cantidad"] - devuelto_final.get(pid, 0) > 0
            for pid, info in vendido.items()
        )
        venta.estado = (
            models.EstadoVentaEnum.CON_DEVOLUCION.value if queda_algo
            else models.EstadoVentaEnum.ANULADA.value
        )

        db.commit()
        db.refresh(devolucion)
        return _armar_respuesta(db, devolucion)

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        # El mensaje interno queda en el log: al cliente le llega uno fijo.
        logger.exception("Error inesperado al registrar una devolución")
        raise HTTPException(status_code=500, detail="No se pudo registrar la devolución")
