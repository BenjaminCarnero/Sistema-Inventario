from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional
from app import models, schemas, database, dependencies

router = APIRouter(prefix="/reportes", tags=["reportes"])

# Los reportes son información de gestión: sólo admin y encargado.
gestor_reportes = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)


def rango_local_en_utc(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """Convierte días del calendario del local a un rango en UTC.

    Las fechas se guardan en UTC, pero un día para el comercio es el día de su
    reloj de pared. Comparando la fecha guardada contra la fecha local, después
    de las 21:00 en Argentina las dos dejan de coincidir y la recaudación del
    día pasaba a mostrar cero: justo en el horario en que más se vende.

    El rango es semiabierto (incluye `desde`, excluye el día siguiente a
    `hasta`) y permite usar el índice de la columna, en vez de calcular una
    función sobre cada fila.
    """
    inicio = datetime.combine(desde, time.min).astimezone(timezone.utc).replace(tzinfo=None)
    fin = (datetime.combine(hasta, time.min) + timedelta(days=1)) \
        .astimezone(timezone.utc).replace(tzinfo=None)
    return inicio, fin


def dia_local_en_utc(dias_atras: int = 0) -> tuple[datetime, datetime]:
    """Rango en UTC del día local de hoy, o de hace tantos días."""
    dia = date.today() - timedelta(days=dias_atras)
    return rango_local_en_utc(dia, dia)


def fecha_local_de(momento_utc: datetime) -> date:
    """Con qué día del local se corresponde un instante guardado en UTC."""
    return momento_utc.replace(tzinfo=timezone.utc).astimezone().date()


@router.get("/kpi", response_model=schemas.KpiResponse)
def get_kpi(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(gestor_reportes)):
    inicio, fin = dia_local_en_utc()

    ventas_hoy = db.query(models.Venta).filter(
        models.Venta.fecha_hora >= inicio,
        models.Venta.fecha_hora < fin,
    ).all()

    # Se descuenta lo devuelto hoy: la recaudación real es lo que quedó en caja,
    # no lo que se facturó antes de las devoluciones.
    devuelto_hoy = db.query(func.sum(models.Devolucion.total_devuelto)).filter(
        models.Devolucion.fecha_hora >= inicio,
        models.Devolucion.fecha_hora < fin,
    ).scalar() or 0.0

    total_recaudado = sum(v.total for v in ventas_hoy) - devuelto_hoy
    cantidad_ventas = len(ventas_hoy)

    if cantidad_ventas > 0:
        metodos = {}
        for v in ventas_hoy:
            metodos[v.metodo_pago] = metodos.get(v.metodo_pago, 0) + 1
        metodo_preferido = max(metodos, key=metodos.get)
    else:
        metodo_preferido = "N/A"

    return schemas.KpiResponse(
        ventas_hoy_local=total_recaudado,
        cantidad_ventas_hoy=cantidad_ventas,
        metodo_pago_preferido=metodo_preferido,
    )


def _devoluciones_por_producto(db: Session) -> dict[int, dict]:
    """Unidades e importe devueltos, por producto. Se usa para netear reportes."""
    filas = db.query(
        models.DetalleDevolucion.producto_id,
        func.sum(models.DetalleDevolucion.cantidad).label("cantidad"),
        func.sum(models.DetalleDevolucion.subtotal).label("importe"),
    ).group_by(models.DetalleDevolucion.producto_id).all()

    return {
        f.producto_id: {"cantidad": f.cantidad or 0, "importe": f.importe or 0.0}
        for f in filas
    }


@router.get("/top_productos", response_model=List[schemas.TopProducto])
def get_top_productos(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(gestor_reportes)):
    resultados = db.query(
        models.Producto.id,
        models.Producto.nombre,
        func.sum(models.DetalleVenta.cantidad).label("cantidad_vendida"),
        func.sum(models.DetalleVenta.subtotal).label("total_recaudado"),
    ).join(models.DetalleVenta, models.Producto.id == models.DetalleVenta.producto_id)\
     .group_by(models.Producto.id).all()

    devueltos = _devoluciones_por_producto(db)

    # Un producto que se vendió y se devolvió no debería figurar como más vendido
    top = []
    for r in resultados:
        dev = devueltos.get(r.id, {"cantidad": 0, "importe": 0.0})
        top.append(schemas.TopProducto(
            id=r.id,
            nombre=r.nombre,
            cantidad_vendida=max(0, (r.cantidad_vendida or 0) - dev["cantidad"]),
            total_recaudado=max(0.0, (r.total_recaudado or 0.0) - dev["importe"]),
        ))

    top.sort(key=lambda x: x.cantidad_vendida, reverse=True)
    return [t for t in top if t.cantidad_vendida > 0][:5]


@router.get("/cajas", response_model=List[schemas.CajaReporte])
def get_historial_cajas(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(gestor_reportes)):
    cajas = db.query(models.CajaTurno).order_by(desc(models.CajaTurno.fecha_apertura)).limit(50).all()

    reporte_cajas = []
    for c in cajas:
        cajero = db.query(models.Usuario).filter(models.Usuario.id == c.usuario_id).first()

        query_ventas = db.query(func.sum(models.Venta.total)).filter(
            models.Venta.usuario_id == c.usuario_id,
            models.Venta.fecha_hora >= c.fecha_apertura,
        )
        if c.fecha_cierre:
            query_ventas = query_ventas.filter(models.Venta.fecha_hora <= c.fecha_cierre)

        reporte_cajas.append(schemas.CajaReporte(
            id=c.id,
            usuario_id=c.usuario_id,
            fecha_apertura=c.fecha_apertura,
            monto_inicial=c.monto_inicial,
            fecha_cierre=c.fecha_cierre,
            monto_final_declarado=c.monto_final_declarado,
            diferencia_calculada=c.diferencia_calculada,
            cajero_nombre=cajero.nombre if cajero else "Desconocido",
            total_ventas_turno=query_ventas.scalar() or 0.0,
        ))

    return reporte_cajas


@router.get("/stock_bajo", response_model=List[schemas.ProductoStockBajo])
def get_stock_bajo(
    umbral: int = Query(5, ge=0, description="Stock por debajo del cual se considera bajo"),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_reportes),
):
    """Productos cuyo stock está por debajo del umbral. Alimenta las alertas
    de disponibilidad del panel de admin/encargado."""
    productos = db.query(models.Producto)\
        .filter(models.Producto.stock_actual < umbral)\
        .order_by(models.Producto.stock_actual.asc())\
        .all()

    return [
        schemas.ProductoStockBajo(
            id=p.id,
            nombre=p.nombre,
            codigo_barras=p.codigo_barras,
            stock_actual=p.stock_actual,
            umbral=umbral,
        )
        for p in productos
    ]


@router.get("/ventas_periodo", response_model=List[schemas.VentaReporte])
def get_ventas_periodo(
    desde: date = Query(..., description="Fecha inicial inclusive (YYYY-MM-DD)"),
    hasta: date = Query(..., description="Fecha final inclusive (YYYY-MM-DD)"),
    cajero_id: Optional[int] = Query(None, description="Filtrar por cajero"),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_reportes),
):
    """Ventas de un período, con detalle de productos. Es la fuente del export a Excel."""
    if desde > hasta:
        raise HTTPException(status_code=400, detail="'desde' no puede ser posterior a 'hasta'")

    # Los días son los del calendario del local; la base guarda UTC
    inicio, limite = rango_local_en_utc(desde, hasta)

    query = db.query(models.Venta).filter(
        models.Venta.fecha_hora >= inicio,
        models.Venta.fecha_hora < limite,
    )
    if cajero_id:
        query = query.filter(models.Venta.usuario_id == cajero_id)

    ventas = query.order_by(models.Venta.fecha_hora.asc()).all()

    # Precargamos usuarios, productos y descuentos para no hacer N+1 consultas
    usuarios = {u.id: u.nombre for u in db.query(models.Usuario).all()}
    productos = {p.id: p.nombre for p in db.query(models.Producto).all()}
    descuentos = {d.id: d.nombre for d in db.query(models.Descuento).all()}

    # Cuánto se devolvió de cada venta del período
    devuelto_por_venta = {
        f.venta_id: f.total or 0.0
        for f in db.query(
            models.Devolucion.venta_id,
            func.sum(models.Devolucion.total_devuelto).label("total"),
        ).group_by(models.Devolucion.venta_id).all()
    }

    resultado = []
    for v in ventas:
        detalles = [
            schemas.DetalleVentaReporte(
                id=d.id,
                venta_id=d.venta_id,
                producto_id=d.producto_id,
                cantidad=d.cantidad,
                precio_unitario=d.precio_unitario,
                subtotal=d.subtotal,
                producto_nombre=productos.get(d.producto_id, "Desconocido"),
            )
            for d in v.detalles
        ]
        resultado.append(schemas.VentaReporte(
            id=v.id,
            usuario_id=v.usuario_id,
            fecha_hora=v.fecha_hora,
            total=v.total,
            metodo_pago=v.metodo_pago,
            monto_recibido=v.monto_recibido,
            vuelto=v.vuelto,
            descuento_id=v.descuento_id,
            descuento_nombre=descuentos.get(v.descuento_id) if v.descuento_id else None,
            iva_porcentaje=v.iva_porcentaje,
            iva_monto=v.iva_monto,
            estado_sincronizacion=v.estado_sincronizacion,
            estado=v.estado,
            total_devuelto=devuelto_por_venta.get(v.id, 0.0),
            cajero_nombre=usuarios.get(v.usuario_id, "Desconocido"),
            detalles=detalles,
        ))

    return resultado


@router.get("/rentabilidad", response_model=List[schemas.RentabilidadProducto])
def get_rentabilidad(
    limite: int = Query(20, ge=1, le=100),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_reportes),
):
    """Ganancia por producto: recaudado menos costo por unidad vendida."""
    resultados = db.query(
        models.Producto.id,
        models.Producto.nombre,
        models.Producto.costo,
        func.sum(models.DetalleVenta.cantidad).label("cantidad_vendida"),
        func.sum(models.DetalleVenta.subtotal).label("total_recaudado"),
    ).join(models.DetalleVenta, models.Producto.id == models.DetalleVenta.producto_id)\
     .group_by(models.Producto.id)\
     .all()

    devueltos = _devoluciones_por_producto(db)

    rentabilidad = []
    for r in resultados:
        # Lo devuelto no se vendió: ni suma ingreso ni consume costo
        dev = devueltos.get(r.id, {"cantidad": 0, "importe": 0.0})
        cantidad = max(0, (r.cantidad_vendida or 0) - dev["cantidad"])
        recaudado = max(0.0, (r.total_recaudado or 0.0) - dev["importe"])
        costo_total = (r.costo or 0.0) * cantidad
        ganancia = recaudado - costo_total
        margen = (ganancia / recaudado * 100) if recaudado else 0.0

        rentabilidad.append(schemas.RentabilidadProducto(
            id=r.id,
            nombre=r.nombre,
            cantidad_vendida=cantidad,
            total_recaudado=recaudado,
            costo_total=costo_total,
            ganancia=ganancia,
            margen_pct=round(margen, 2),
        ))

    rentabilidad.sort(key=lambda x: x.ganancia, reverse=True)
    return rentabilidad[:limite]


@router.get("/ventas_por_dia")
def get_ventas_por_dia(
    dias: int = Query(14, ge=1, le=90),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_reportes),
):
    """Serie temporal de recaudación diaria para el gráfico del dashboard.
    Devuelve todos los días del rango, incluidos los que no tuvieron ventas."""
    hoy = date.today()
    inicio = hoy - timedelta(days=dias - 1)

    desde_utc, hasta_utc = rango_local_en_utc(inicio, hoy)

    # Se agrupa en Python y no con func.date(): la base guarda UTC, así que
    # agrupar por la fecha guardada corre las ventas de la noche al día
    # siguiente. Para el rango que muestra el gráfico el volumen es chico.
    ventas = db.query(models.Venta.fecha_hora, models.Venta.total).filter(
        models.Venta.fecha_hora >= desde_utc,
        models.Venta.fecha_hora < hasta_utc,
    ).all()

    por_dia: dict[str, dict] = {}
    for fecha_hora, total in ventas:
        clave = fecha_local_de(fecha_hora).isoformat()
        acumulado = por_dia.setdefault(clave, {"total": 0.0, "cantidad": 0})
        acumulado["total"] += total or 0.0
        acumulado["cantidad"] += 1

    serie = []
    for i in range(dias):
        d = inicio + timedelta(days=i)
        datos = por_dia.get(d.isoformat(), {"total": 0.0, "cantidad": 0})
        serie.append({
            "fecha": d.isoformat(),
            "etiqueta": d.strftime("%d/%m"),
            "total": datos["total"],
            "cantidad": datos["cantidad"],
        })

    return serie


@router.get("/cajas/{caja_id}/ventas", response_model=List[schemas.VentaReporte])
def get_ventas_caja(
    caja_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_reportes),
):
    caja = db.query(models.CajaTurno).filter(models.CajaTurno.id == caja_id).first()
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada")

    query_ventas = db.query(models.Venta).filter(
        models.Venta.usuario_id == caja.usuario_id,
        models.Venta.fecha_hora >= caja.fecha_apertura,
    )
    if caja.fecha_cierre:
        query_ventas = query_ventas.filter(models.Venta.fecha_hora <= caja.fecha_cierre)

    # Cuánto se devolvió de cada venta, para mostrarlo en el detalle del turno
    devuelto_caja = {
        f.venta_id: f.total or 0.0
        for f in db.query(
            models.Devolucion.venta_id,
            func.sum(models.Devolucion.total_devuelto).label("total"),
        ).group_by(models.Devolucion.venta_id).all()
    }

    ventas_reporte = []
    for v in query_ventas.all():
        detalles_reporte = []
        for d in v.detalles:
            producto = db.query(models.Producto).filter(models.Producto.id == d.producto_id).first()
            detalles_reporte.append(schemas.DetalleVentaReporte(
                id=d.id,
                venta_id=d.venta_id,
                producto_id=d.producto_id,
                cantidad=d.cantidad,
                precio_unitario=d.precio_unitario,
                subtotal=d.subtotal,
                producto_nombre=producto.nombre if producto else "Desconocido",
            ))

        descuento = None
        if v.descuento_id:
            descuento = db.query(models.Descuento).filter(models.Descuento.id == v.descuento_id).first()

        ventas_reporte.append(schemas.VentaReporte(
            id=v.id,
            usuario_id=v.usuario_id,
            fecha_hora=v.fecha_hora,
            total=v.total,
            metodo_pago=v.metodo_pago,
            monto_recibido=v.monto_recibido,
            vuelto=v.vuelto,
            descuento_id=v.descuento_id,
            descuento_nombre=descuento.nombre if descuento else None,
            iva_porcentaje=v.iva_porcentaje,
            estado=v.estado,
            total_devuelto=devuelto_caja.get(v.id, 0.0),
            iva_monto=v.iva_monto,
            estado_sincronizacion=v.estado_sincronizacion,
            detalles=detalles_reporte,
        ))

    return ventas_reporte
