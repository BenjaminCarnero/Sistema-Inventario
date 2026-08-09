from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, date, timedelta
from typing import List, Optional
from app import models, schemas, database, dependencies

router = APIRouter(prefix="/reportes", tags=["reportes"])

# Los reportes son información de gestión: sólo admin y encargado.
get_admin_user = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)


@router.get("/kpi", response_model=schemas.KpiResponse)
def get_kpi(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(get_admin_user)):
    hoy = date.today()

    ventas_hoy = db.query(models.Venta).filter(func.date(models.Venta.fecha_hora) == hoy).all()

    total_recaudado = sum(v.total for v in ventas_hoy)
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


@router.get("/top_productos", response_model=List[schemas.TopProducto])
def get_top_productos(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(get_admin_user)):
    resultados = db.query(
        models.Producto.id,
        models.Producto.nombre,
        func.sum(models.DetalleVenta.cantidad).label("cantidad_vendida"),
        func.sum(models.DetalleVenta.subtotal).label("total_recaudado"),
    ).join(models.DetalleVenta, models.Producto.id == models.DetalleVenta.producto_id)\
     .group_by(models.Producto.id)\
     .order_by(desc("cantidad_vendida"))\
     .limit(5).all()

    return [
        schemas.TopProducto(
            id=r.id,
            nombre=r.nombre,
            cantidad_vendida=r.cantidad_vendida or 0,
            total_recaudado=r.total_recaudado or 0.0,
        )
        for r in resultados
    ]


@router.get("/cajas", response_model=List[schemas.CajaReporte])
def get_historial_cajas(db: Session = Depends(database.get_db), current_user: models.Usuario = Depends(get_admin_user)):
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
    current_user: models.Usuario = Depends(get_admin_user),
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
    current_user: models.Usuario = Depends(get_admin_user),
):
    """Ventas de un período, con detalle de productos. Es la fuente del export a Excel."""
    if desde > hasta:
        raise HTTPException(status_code=400, detail="'desde' no puede ser posterior a 'hasta'")

    # hasta es inclusive: comparamos contra el inicio del día siguiente
    limite = datetime.combine(hasta, datetime.min.time()) + timedelta(days=1)
    inicio = datetime.combine(desde, datetime.min.time())

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
            cajero_nombre=usuarios.get(v.usuario_id, "Desconocido"),
            detalles=detalles,
        ))

    return resultado


@router.get("/rentabilidad", response_model=List[schemas.RentabilidadProducto])
def get_rentabilidad(
    limite: int = Query(20, ge=1, le=100),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(get_admin_user),
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

    rentabilidad = []
    for r in resultados:
        cantidad = r.cantidad_vendida or 0
        recaudado = r.total_recaudado or 0.0
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
    current_user: models.Usuario = Depends(get_admin_user),
):
    """Serie temporal de recaudación diaria para el gráfico del dashboard.
    Devuelve todos los días del rango, incluidos los que no tuvieron ventas."""
    hoy = date.today()
    inicio = hoy - timedelta(days=dias - 1)

    filas = db.query(
        func.date(models.Venta.fecha_hora).label("dia"),
        func.sum(models.Venta.total).label("total"),
        func.count(models.Venta.id).label("cantidad"),
    ).filter(func.date(models.Venta.fecha_hora) >= inicio)\
     .group_by("dia").all()

    por_dia = {str(f.dia): {"total": f.total or 0.0, "cantidad": f.cantidad or 0} for f in filas}

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
    current_user: models.Usuario = Depends(get_admin_user),
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
            iva_monto=v.iva_monto,
            estado_sincronizacion=v.estado_sincronizacion,
            detalles=detalles_reporte,
        ))

    return ventas_reporte
