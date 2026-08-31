"""De dónde viene realmente una petición.

`request.client.host` es la IP de quien abrió la conexión TCP. Con la
aplicación expuesta directo eso es el cliente, pero detrás de un reverse proxy
—que es como va a estar en cuanto se publique— es siempre la IP del proxy.

Eso rompe los dos frenos que cuentan por IP: el de barrido de cuentas
bloquearía a todo el comercio de una, y el de peticiones dejaría de distinguir
a nadie. Por eso la IP se resuelve acá y en un solo lugar, y no en cada router.
"""
from typing import Optional

from app.config import settings

DESCONOCIDA = "desconocida"


def ip_del_cliente(request) -> str:
    """IP real de quien hizo la petición.

    Con `PROXIES_CONFIABLES = 0` se usa la del socket y se ignora cualquier
    cabecera: un cliente puede mandar `X-Forwarded-For` con lo que se le
    ocurra, así que confiar en ella sin proxy delante es peor que no tenerla.

    Con N proxies propios se toma la entrada N-ésima **desde la derecha**. La
    cadena es `cliente, proxy1, proxy2, …` y cada proxy agrega al final la IP
    de quien le habló: el cliente puede inventar las de la izquierda, pero no
    las que escribieron nuestros propios proxies.
    """
    saltos = settings.PROXIES_CONFIABLES

    if saltos > 0:
        cadena = request.headers.get("x-forwarded-for", "")
        partes = [p.strip() for p in cadena.split(",") if p.strip()]
        if partes:
            # Si llegan menos entradas de las esperadas, se usa la más a la
            # izquierda que haya en vez de fallar: es lo más cercano al cliente
            # que se puede afirmar con lo que llegó.
            indice = max(0, len(partes) - saltos)
            return partes[indice]

    return _ip_del_socket(request)


def _ip_del_socket(request) -> str:
    cliente: Optional[object] = getattr(request, "client", None)
    host = getattr(cliente, "host", None) if cliente else None
    return host or DESCONOCIDA
