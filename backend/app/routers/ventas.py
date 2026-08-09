from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app import models, schemas, database, dependencies
from app.routers.configuracion import obtener_config

router = APIRouter(prefix="/ventas", tags=["ventas"])

# Límites de una venta razonable. Sin techo, un pedido armado a mano puede
# dejar al servidor procesando miles de líneas y tumbar la caja.
MAX_LINEAS = 200
MAX_CANTIDAD_POR_LINEA = 10_000

METODOS_VALIDOS = {m.value for m in models.MetodoPagoEnum} | {"MERCADOPAGO"}


@router.post("/", response_model=schemas.Venta, status_code=status.HTTP_201_CREATED)
def create_venta(
    venta: schemas.VentaCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    # Iniciar transacción ACID (automático en SQLAlchemy con session)
    try:
        config = obtener_config(db)

        # --- Validaciones de entrada ---------------------------------------
        if not venta.detalles:
            raise HTTPException(status_code=400, detail="La venta no tiene productos")

        if len(venta.detalles) > MAX_LINEAS:
            raise HTTPException(
                status_code=400,
                detail=f"La venta supera el máximo de {MAX_LINEAS} líneas"
            )

        if venta.metodo_pago not in METODOS_VALIDOS:
            raise HTTPException(
                status_code=400,
                detail=f"Método de pago inválido. Válidos: {', '.join(sorted(METODOS_VALIDOS))}"
            )

        for detalle in venta.detalles:
            if detalle.cantidad <= 0:
                raise HTTPException(status_code=400, detail="Las cantidades tienen que ser mayores a cero")
            if detalle.cantidad > MAX_CANTIDAD_POR_LINEA:
                raise HTTPException(
                    status_code=400,
                    detail=f"La cantidad por producto no puede superar {MAX_CANTIDAD_POR_LINEA}"
                )

        # El tope también se valida acá: el cliente puede estar desactualizado
        # o la venta puede llegar desde una sincronización offline.
        tope = float(config.get("monto_maximo_efectivo") or 1_000_000)
        if venta.monto_recibido is not None:
            if venta.monto_recibido < 0:
                raise HTTPException(status_code=400, detail="El monto recibido no puede ser negativo")
            if venta.monto_recibido > tope:
                raise HTTPException(
                    status_code=400,
                    detail=f"El monto recibido supera el tope configurado ({tope:,.0f})"
                )

        # --- Idempotencia ---------------------------------------------------
        # El POS manda un identificador propio por venta. Si la sincronización
        # se reintenta (red intermitente), se devuelve la venta ya registrada
        # en lugar de cobrarla otra vez.
        if venta.uuid_cliente:
            existente = db.query(models.Venta).filter(
                models.Venta.uuid_cliente == venta.uuid_cliente
            ).first()
            if existente:
                return existente

        total_venta = 0
        db_venta = models.Venta(
            usuario_id=current_user.id,
            metodo_pago=venta.metodo_pago,
            monto_recibido=venta.monto_recibido,
            vuelto=venta.vuelto,
            descuento_id=venta.descuento_id,
            uuid_cliente=venta.uuid_cliente,
            estado_sincronizacion=venta.estado_sincronizacion,
            total=0,  # Se calculará ahora
        )
        db.add(db_venta)
        db.flush()  # Para obtener db_venta.id

        for detalle in venta.detalles:
            # Bloquear la fila del producto (SELECT FOR UPDATE) para evitar race conditions
            producto = db.query(models.Producto).filter(
                models.Producto.id == detalle.producto_id
            ).with_for_update().first()
            if not producto:
                raise HTTPException(status_code=404, detail=f"Producto {detalle.producto_id} no encontrado")

            # Por defecto se permite stock negativo (el cajero ya entregó el
            # producto físico), pero se puede exigir stock desde configuración.
            if not config.get("permitir_stock_negativo", True) and producto.stock_actual < detalle.cantidad:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock_actual}"
                )
            producto.stock_actual -= detalle.cantidad

            # El precio SIEMPRE sale del catálogo del servidor. Lo que manda el
            # cliente es sólo informativo: si se confiara en él, cualquiera con
            # acceso a la API podría cobrarse un producto de $2000 a $1.
            precio_unitario = producto.precio_venta
            subtotal = detalle.cantidad * precio_unitario
            total_venta += subtotal

            db.add(models.DetalleVenta(
                venta_id=db_venta.id,
                producto_id=detalle.producto_id,
                cantidad=detalle.cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal,
            ))

            # Registrar el movimiento de stock (Egreso por venta)
            db.add(models.MovimientoStock(
                producto_id=producto.id,
                usuario_id=current_user.id,
                tipo_movimiento=models.TipoMovimientoEnum.EGRESO.value,
                cantidad=detalle.cantidad,
                motivo=f"Venta #{db_venta.id}",
            ))

        # Aplicar descuento si la venta trae uno. El total se recalcula acá en el
        # servidor y no se confía en lo que mandó el cliente.
        if venta.descuento_id:
            descuento = db.query(models.Descuento).filter(
                models.Descuento.id == venta.descuento_id
            ).first()
            if not descuento:
                raise HTTPException(status_code=404, detail="Descuento no encontrado")
            if not descuento.activo:
                raise HTTPException(status_code=400, detail="El descuento no está activo")

            ahora = datetime.now()
            if descuento.fecha_inicio and ahora < descuento.fecha_inicio:
                raise HTTPException(status_code=400, detail="El descuento todavía no está vigente")
            if descuento.fecha_fin and ahora > descuento.fecha_fin:
                raise HTTPException(status_code=400, detail="El descuento está vencido")

            if descuento.producto_id:
                # Descuento por producto: sólo sobre las líneas de ese producto
                base = sum(
                    d.cantidad * (db.query(models.Producto).get(d.producto_id).precio_venta)
                    for d in venta.detalles
                    if d.producto_id == descuento.producto_id
                )
            else:
                base = total_venta

            if descuento.tipo == "PORCENTAJE":
                rebaja = base * (descuento.valor / 100)
            else:
                rebaja = min(descuento.valor, base)

            total_venta = max(0.0, round(total_venta - rebaja, 2))

        # IVA según la configuración vigente. Se guarda la alícuota usada para
        # que un cambio futuro no altere los tickets ya emitidos.
        iva_pct = float(config.get("iva_porcentaje") or 0)

        if iva_pct > 0:
            if config.get("iva_incluido_en_precio", True):
                # El precio de góndola ya trae el IVA adentro (caso Argentina):
                # el total no cambia, sólo se calcula cuánto de ese total es impuesto.
                neto = total_venta / (1 + iva_pct / 100)
                iva_monto = total_venta - neto
            else:
                # El precio es neto y el impuesto se suma al cobrar (caso EE.UU.).
                iva_monto = total_venta * (iva_pct / 100)
                total_venta = total_venta + iva_monto
            db_venta.iva_porcentaje = iva_pct
            db_venta.iva_monto = round(iva_monto, 2)

        db_venta.total = round(total_venta, 2)
        db.commit()
        db.refresh(db_venta)
        return db_venta

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[schemas.Venta])
def read_ventas(
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Ventas visibles para el usuario.

    Un cajero sólo ve las suyas; admin y encargado ven las de todo el local.
    """
    query = db.query(models.Venta)
    if current_user.rol_id == models.RolEnum.CAJERO.value:
        query = query.filter(models.Venta.usuario_id == current_user.id)

    return query.order_by(models.Venta.id.desc()).offset(skip).limit(limit).all()
