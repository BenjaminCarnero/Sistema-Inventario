import logging
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app import models, schemas, database, dependencies
from app.routers.configuracion import obtener_config
from app.routers import pagos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ventas", tags=["ventas"])

# Límites de una venta razonable. Sin techo, un pedido armado a mano puede
# dejar al servidor procesando miles de líneas y tumbar la caja.
MAX_LINEAS = 200
MAX_CANTIDAD_POR_LINEA = 10_000

METODOS_VALIDOS = {m.value for m in models.MetodoPagoEnum} | {"MERCADOPAGO"}


def _confirmar_cobro_por_qr(db: Session, referencia: str, total: float, venta_id: int) -> str:
    """Comprueba contra Mercado Pago que el cobro por QR realmente entró.

    El chequeo va acá y no en el cliente porque acá el total no es negociable:
    es el que acaba de calcular el servidor con los precios del catálogo. Antes
    alcanzaba con mandar `metodo_pago=MERCADOPAGO` para dar por cobrada una
    venta sin que hubiera entrado un peso, y sin dejar rastro para conciliar.
    """
    referencia = (referencia or "").strip()
    if not referencia:
        raise HTTPException(
            status_code=400,
            detail="Una venta por Mercado Pago tiene que traer la referencia del cobro",
        )

    # Una referencia respalda una sola venta: si no, un único pago de $50.000
    # podría cerrar todas las ventas que se quisieran.
    repetida = db.query(models.Venta).filter(
        models.Venta.pago_referencia == referencia,
        models.Venta.id != venta_id,
    ).first()
    if repetida:
        raise HTTPException(
            status_code=409,
            detail=f"Ese cobro de Mercado Pago ya respalda la venta #{repetida.id}",
        )

    pagado = pagos.total_aprobado(referencia)
    if not pagos.alcanza(pagado, total):
        raise HTTPException(
            status_code=402,
            detail=(
                f"Mercado Pago no registra el cobro completo: "
                f"acreditado {pagado:.2f} de {total:.2f}"
            ),
        )
    return referencia


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

        # El descuento se valida acá, antes de escribir nada. Estaba más abajo,
        # después de haber insertado la venta y descontado el stock: con las
        # claves foráneas activadas, un descuento inexistente ni siquiera
        # llegaba a esa comprobación y moría con un error de integridad en vez
        # del mensaje que corresponde.
        descuento = None
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
        # La referencia del QR se asigna recién después de confirmar el cobro,
        # más abajo: hasta entonces la venta no está pagada.
        db.add(db_venta)
        db.flush()  # Para obtener db_venta.id

        # Lo que ya comprometió esta misma venta, por producto. Hace falta
        # llevarlo aparte porque la resta la hace la base: el objeto que tenemos
        # en memoria se queda con el valor viejo, y un producto repetido en dos
        # líneas se validaría dos veces contra el mismo stock inicial.
        comprometido: dict[int, int] = {}

        for detalle in venta.detalles:
            producto = db.query(models.Producto).filter(
                models.Producto.id == detalle.producto_id
            ).first()
            if not producto:
                raise HTTPException(status_code=404, detail=f"Producto {detalle.producto_id} no encontrado")

            # Por defecto se permite stock negativo (el cajero ya entregó el
            # producto físico), pero se puede exigir stock desde configuración.
            disponible = producto.stock_actual - comprometido.get(detalle.producto_id, 0)
            if not config.get("permitir_stock_negativo", True) and disponible < detalle.cantidad:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente para {producto.nombre}. Disponible: {disponible}"
                )
            comprometido[detalle.producto_id] = comprometido.get(detalle.producto_id, 0) + detalle.cantidad

            # La resta la hace la base y no Python. Acá antes había un
            # `with_for_update()`, pero SQLite lo descarta en silencio —compila
            # a un SELECT pelado— así que dos cajas vendiendo el mismo producto
            # a la vez leían el mismo stock y las dos escribían el mismo valor:
            # se perdía una unidad sin que nadie se enterara.
            db.query(models.Producto).filter(
                models.Producto.id == detalle.producto_id
            ).update(
                {models.Producto.stock_actual: models.Producto.stock_actual - detalle.cantidad},
                synchronize_session=False,
            )

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
        if descuento is not None:
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

        # El cobro por QR se confirma contra Mercado Pago con el total recién
        # calculado. Si no está acreditado, la excepción hace rollback y el
        # stock descontado más arriba vuelve a su lugar.
        if venta.metodo_pago == "MERCADOPAGO":
            db_venta.pago_referencia = _confirmar_cobro_por_qr(
                db, venta.pago_referencia, db_venta.total, db_venta.id
            )

        db.commit()
        db.refresh(db_venta)
        return db_venta

    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        # Los índices únicos de `pago_referencia` y `uuid_cliente` frenaron una
        # carrera: dos pedidos simultáneos con el mismo cobro o la misma venta.
        # Uno de los dos entró, y este es el que perdió.
        logger.warning("Choque de unicidad al registrar una venta", exc_info=True)
        raise HTTPException(
            status_code=409,
            detail="Esa venta o ese cobro ya quedaron registrados",
        )
    except Exception:
        db.rollback()
        # El detalle va al log del servidor y no a la respuesta: el mensaje de
        # SQLAlchemy trae el SQL, los nombres de las tablas y a veces rutas del
        # disco. En producción se cierra /docs justamente para no regalar eso.
        logger.exception("Error inesperado al registrar una venta")
        raise HTTPException(status_code=500, detail="No se pudo registrar la venta")


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
