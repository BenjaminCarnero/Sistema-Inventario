from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import models, database, dependencies, impresora
from app.routers.configuracion import obtener_config
from app.ticket_escpos import DatosTicket, ItemTicket, generar_ticket

router = APIRouter(prefix="/impresion", tags=["impresion"])


def _datos_del_ticket(db: Session, venta: models.Venta, config: dict) -> DatosTicket:
    """Arma el ticket con lo que la propia venta tiene guardado — no con nada
    que mande quien imprime. Es un comprobante de algo que ya se cobró: el
    servidor no vuelve a "decidir" nada acá, sólo lee lo que ya decidió antes.
    """
    items = [
        ItemTicket(
            cantidad=d.cantidad,
            nombre=d.producto.nombre if d.producto else f"Producto #{d.producto_id}",
            precio_unitario=d.precio_unitario,
            subtotal=d.subtotal,
        )
        for d in venta.detalles
    ]

    descuento_nombre = ""
    descuento_monto = 0.0
    if venta.descuento_id:
        descuento = db.query(models.Descuento).filter(models.Descuento.id == venta.descuento_id).first()
        if descuento:
            descuento_nombre = descuento.nombre
            subtotal_bruto = sum(d.subtotal for d in venta.detalles)
            iva_si_no_incluido = venta.iva_monto if not config.get("iva_incluido_en_precio") else 0
            descuento_monto = subtotal_bruto - venta.total + iva_si_no_incluido

    return DatosTicket(
        negocio_nombre=config.get("negocio_nombre") or "",
        negocio_direccion=config.get("negocio_direccion") or "",
        negocio_telefono=config.get("negocio_telefono") or "",
        negocio_cuit=config.get("negocio_cuit") or "",
        fecha_hora_texto=venta.fecha_hora.strftime("%d/%m/%Y %H:%M") if venta.fecha_hora else "",
        items=items,
        total=venta.total,
        metodo_pago=venta.metodo_pago,
        numero_operacion=venta.id,
        moneda_simbolo=config.get("moneda_simbolo") or "$",
        descuento_nombre=descuento_nombre,
        descuento_monto=descuento_monto,
        mostrar_iva=bool(config.get("mostrar_iva_en_ticket")) and bool(venta.iva_monto),
        iva_nombre=config.get("iva_nombre") or "IVA",
        iva_porcentaje=venta.iva_porcentaje or 0,
        iva_monto=venta.iva_monto or 0,
        monto_recibido=venta.monto_recibido,
        vuelto=venta.vuelto,
        mensaje_pie=config.get("ticket_mensaje_pie") or "",
        abrir_cajon=bool(config.get("impresora_abrir_cajon")),
        ancho_caracteres=int(config.get("impresora_ancho_caracteres") or 42),
    )


@router.post("/venta/{venta_id}")
def imprimir_venta(
    venta_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Imprime el ticket de una venta ya registrada en la térmica configurada.

    Cualquier usuario logueado puede imprimir: es lo mismo que hoy hace
    cualquier cajero apretando "Imprimir" en el diálogo del navegador.
    """
    venta = db.query(models.Venta).filter(models.Venta.id == venta_id).first()
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    config = obtener_config(db)
    if not config.get("impresora_habilitada"):
        raise HTTPException(
            status_code=400,
            detail="La impresora térmica no está habilitada. Activala en Configuración › Impresora térmica.",
        )

    datos = _datos_del_ticket(db, venta, config)
    ticket = generar_ticket(datos)

    try:
        impresora.enviar(
            ip=config.get("impresora_ip") or "",
            puerto=int(config.get("impresora_puerto") or 9100),
            datos=ticket,
        )
    except impresora.ErrorDeImpresion as error:
        raise HTTPException(status_code=502, detail=str(error))

    return {"impreso": True, "venta_id": venta_id}


@router.get("/venta/{venta_id}/previsualizar")
def previsualizar_venta(
    venta_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """Devuelve los bytes ESC/POS crudos, sin mandarlos a ninguna impresora.

    Sirve para probar el formato del ticket contra un archivo o un emulador
    ESC/POS sin depender de tener la térmica prendida y en red.
    """
    venta = db.query(models.Venta).filter(models.Venta.id == venta_id).first()
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    config = obtener_config(db)
    datos = _datos_del_ticket(db, venta, config)
    ticket = generar_ticket(datos)
    return Response(content=ticket, media_type="application/octet-stream")
