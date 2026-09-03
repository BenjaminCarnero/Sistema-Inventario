"""Entrega de los bytes ESC/POS a la impresora física.

Separado de `ticket_escpos.py` a propósito: armar el ticket es lógica pura que
se prueba sin hardware; mandarlo es lo único que de verdad necesita una
impresora conectada — o, para probarlo, un servidor TCP que haga de impresora.

Por qué por red (puerto 9100, el "raw" o "JetDirect" que traen prácticamente
todas las térmicas con Ethernet o WiFi) y no por USB: el backend puede correr
en una PC distinta de donde está enchufada la impresora, y una conexión de
socket es la misma línea de código sirva la impresora que esté en la misma
máquina o en otra del local. Impresión por USB local queda pendiente (ver
PARA-PRODUCCION.md §3): necesitaría `pywin32` y no hay forma de probarla sin
una impresora real conectada a esta máquina.
"""
import logging
import socket

logger = logging.getLogger(__name__)


class ErrorDeImpresion(Exception):
    """La impresora no contestó, o contestó mal. El texto es para mostrarlo
    al cajero tal cual: no debe revelar direcciones IP internas de más, pero
    sí decir qué está pasando."""


def enviar(ip: str, puerto: int, datos: bytes, timeout_segundos: float = 5.0) -> None:
    if not ip:
        raise ErrorDeImpresion("No hay una impresora configurada.")

    try:
        with socket.create_connection((ip, puerto), timeout=timeout_segundos) as conexion:
            conexion.sendall(datos)
    except (socket.timeout, TimeoutError) as error:
        logger.warning("Timeout imprimiendo en %s:%s: %s", ip, puerto, error)
        raise ErrorDeImpresion("La impresora no contestó a tiempo. ¿Está prendida y en la red?") from error
    except OSError as error:
        logger.warning("Error de red imprimiendo en %s:%s: %s", ip, puerto, error)
        raise ErrorDeImpresion("No se pudo conectar con la impresora. Revisá la IP y que esté en la misma red.") from error
