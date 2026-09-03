"""Arma el ticket en comandos ESC/POS crudos, para imprimir en una térmica de
verdad en vez del diálogo del navegador (`window.print()`).

Nada de esto depende de FastAPI, SQLAlchemy ni de tener una impresora
conectada: son funciones puras que arman bytes a partir de un diccionario ya
armado. Eso es lo que permite probarlo byte a byte sin hardware — la parte que
sí necesita un lector real (`impresora.py`, mandar los bytes por red) queda
separada a propósito.

Comandos usados, para quien tenga que tocar esto sin el manual al lado:
  ESC @        (1B 40)        reset de la impresora
  ESC a n      (1B 61 n)      alineación: 0 izquierda, 1 centro, 2 derecha
  ESC E n      (1B 45 n)      negrita on/off
  GS ! n       (1D 21 n)      tamaño de letra (0x11 = doble ancho y alto)
  ESC t n      (1B 74 n)      tabla de caracteres (16 = WPC1252, con acentos)
  GS V m       (1D 56 m)      corte de papel (1 = parcial)
  ESC p m t1t2 (1B 70 ...)    abre el cajón de dinero

La tabla de códigos (WPC1252) es la de Epson y la que imitan casi todos los
clones baratos, pero no hay dos modelos iguales: si en la impresora real sale
con acentos mal, es el primer lugar donde mirar.
"""
from dataclasses import dataclass, field

ESC = b"\x1b"
GS = b"\x1d"

RESET = ESC + b"@"
ALINEAR_IZQUIERDA = ESC + b"a" + b"\x00"
ALINEAR_CENTRO = ESC + b"a" + b"\x01"
ALINEAR_DERECHA = ESC + b"a" + b"\x02"
NEGRITA_ON = ESC + b"E" + b"\x01"
NEGRITA_OFF = ESC + b"E" + b"\x00"
TAMANO_NORMAL = GS + b"!" + b"\x00"
TAMANO_DOBLE = GS + b"!" + b"\x11"
TABLA_WPC1252 = ESC + b"t" + b"\x10"
CORTE_PARCIAL = GS + b"V" + b"\x01"
ABRIR_CAJON = ESC + b"p" + b"\x00" + b"\x19" + b"\xfa"  # pin 2, ~50ms/500ms

_CODIFICACION = "cp1252"


def _texto(linea: str) -> bytes:
    return linea.encode(_CODIFICACION, errors="replace") + b"\n"


def _separador(ancho: int) -> bytes:
    return _texto("-" * ancho)


def _linea_dos_columnas(izquierda: str, derecha: str, ancho: int) -> bytes:
    """Etiqueta a la izquierda, importe a la derecha, como una fila de ticket.

    Si no entran las dos en el ancho de la impresora, la izquierda se recorta
    en vez de partir la línea: una línea de más rompe el resto del ticket.
    """
    espacio = ancho - len(derecha)
    if espacio < 1:
        return _texto((izquierda + derecha)[:ancho])
    return _texto(izquierda[:espacio - 1].ljust(espacio) + derecha)


@dataclass
class ItemTicket:
    cantidad: int
    nombre: str
    precio_unitario: float
    subtotal: float


@dataclass
class DatosTicket:
    """Todo lo que hace falta para imprimir un ticket, ya resuelto.

    Se arma en el router a partir de la venta guardada en la base — no de lo
    que mande el cliente — porque el ticket es un comprobante de algo que ya
    se cobró: no hay nada que "decidir" acá, sólo formatear números que el
    servidor ya calculó en su momento.
    """
    negocio_nombre: str
    items: list  # de ItemTicket
    total: float
    metodo_pago: str
    numero_operacion: int
    moneda_simbolo: str = "$"
    negocio_direccion: str = ""
    negocio_telefono: str = ""
    negocio_cuit: str = ""
    fecha_hora_texto: str = ""
    descuento_nombre: str = ""
    descuento_monto: float = 0.0
    mostrar_iva: bool = False
    iva_nombre: str = "IVA"
    iva_porcentaje: float = 0.0
    iva_monto: float = 0.0
    monto_recibido: float = None
    vuelto: float = None
    mensaje_pie: str = ""
    abrir_cajon: bool = False
    ancho_caracteres: int = 42


def _moneda(valor: float, simbolo: str) -> str:
    return f"{simbolo}{valor:,.2f}"


def generar_ticket(datos: DatosTicket) -> bytes:
    ancho = datos.ancho_caracteres
    m = lambda v: _moneda(v, datos.moneda_simbolo)  # noqa: E731

    partes = [RESET, TABLA_WPC1252, ALINEAR_CENTRO]

    partes.append(TAMANO_DOBLE + NEGRITA_ON)
    partes.append(_texto(datos.negocio_nombre))
    partes.append(NEGRITA_OFF + TAMANO_NORMAL)

    if datos.negocio_direccion:
        partes.append(_texto(datos.negocio_direccion))
    if datos.negocio_telefono:
        partes.append(_texto(f"Tel: {datos.negocio_telefono}"))
    if datos.negocio_cuit:
        partes.append(_texto(f"CUIT: {datos.negocio_cuit}"))
    partes.append(_texto("Ticket de Venta"))
    if datos.fecha_hora_texto:
        partes.append(_texto(datos.fecha_hora_texto))
    partes.append(_texto(f"Operación N° {datos.numero_operacion}"))

    partes.append(ALINEAR_IZQUIERDA)
    partes.append(_separador(ancho))
    for item in datos.items:
        partes.append(_texto(f"{item.cantidad}x {item.nombre}"))
        partes.append(_linea_dos_columnas(f"  {m(item.precio_unitario)} c/u", m(item.subtotal), ancho))
    partes.append(_separador(ancho))

    if datos.descuento_nombre and datos.descuento_monto:
        partes.append(_linea_dos_columnas(datos.descuento_nombre, f"-{m(datos.descuento_monto)}", ancho))

    if datos.mostrar_iva and datos.iva_monto:
        partes.append(_linea_dos_columnas("Neto gravado", m(datos.total - datos.iva_monto), ancho))
        partes.append(_linea_dos_columnas(f"{datos.iva_nombre} {datos.iva_porcentaje}%", m(datos.iva_monto), ancho))

    partes.append(NEGRITA_ON + TAMANO_DOBLE)
    partes.append(_linea_dos_columnas("TOTAL", m(datos.total), ancho // 2))
    partes.append(TAMANO_NORMAL + NEGRITA_OFF)

    if datos.metodo_pago == "EFECTIVO" and datos.monto_recibido is not None and datos.vuelto is not None:
        partes.append(_linea_dos_columnas("Recibido", m(datos.monto_recibido), ancho))
        partes.append(NEGRITA_ON)
        partes.append(_linea_dos_columnas("VUELTO", m(datos.vuelto), ancho))
        partes.append(NEGRITA_OFF)
    else:
        partes.append(ALINEAR_DERECHA)
        partes.append(_texto(f"Abonado con {datos.metodo_pago}"))
        partes.append(ALINEAR_IZQUIERDA)

    partes.append(ALINEAR_CENTRO)
    if datos.mensaje_pie:
        partes.append(_texto(""))
        partes.append(_texto(datos.mensaje_pie))

    partes.append(_texto(""))
    partes.append(_texto(""))
    partes.append(CORTE_PARCIAL)

    if datos.abrir_cajon:
        partes.append(ABRIR_CAJON)

    return b"".join(partes)
