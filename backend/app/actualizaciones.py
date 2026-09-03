"""Chequeo de versión nueva contra GitHub Releases.

Sólo mira si hay algo más nuevo: bajar, migrar y reiniciar el servicio lo hace
`installer/scripts/actualizar.ps1`, que corre con el backend parado y no puede
depender de que el propio backend esté vivo para actuar.

Igual que el chequeo de licencia (ver PARA-PRODUCCION.md §9): si GitHub no
contesta, el comercio sigue vendiendo con la versión que tiene. Avisar de una
actualización nunca puede ser una condición para poder cobrar.
"""
import logging
import re

import requests

from app.config import VERSION

logger = logging.getLogger(__name__)

REPOSITORIO = "BenjaminCarnero/Sistema-Inventario"
_URL_LATEST = f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"
_TIMEOUT_SEGUNDOS = 5


def _a_tupla(version: str) -> tuple:
    """"0.2.10" -> (0, 2, 10). Lo que no es un número se ignora, para no
    romper contra un tag con sufijo tipo "0.2.0-beta"."""
    numeros = re.findall(r"\d+", version)
    return tuple(int(n) for n in numeros) or (0,)


def buscar_disponible() -> dict:
    """Compara la versión instalada contra la última publicada en GitHub.

    Nunca lanza: cualquier problema (sin red, repo sin releases todavía, la
    API de GitHub caída o limitando por rate limit) se traduce en "no hay
    actualización", no en un error que el POS tenga que manejar.
    """
    resultado = {
        "version_actual": VERSION,
        "version_disponible": None,
        "hay_actualizacion": False,
        "url": None,
    }

    try:
        respuesta = requests.get(
            _URL_LATEST,
            headers={"Accept": "application/vnd.github+json"},
            timeout=_TIMEOUT_SEGUNDOS,
        )
        if respuesta.status_code != 200:
            # 404 típico: el repositorio todavía no tiene ningún release publicado.
            return resultado

        datos = respuesta.json()
        tag = str(datos.get("tag_name", "")).strip()
        if not tag:
            return resultado

        version_remota = tag[1:] if tag.lower().startswith("v") else tag
        resultado["version_disponible"] = version_remota
        resultado["url"] = datos.get("html_url")
        resultado["hay_actualizacion"] = _a_tupla(version_remota) > _a_tupla(VERSION)
        return resultado

    except (requests.RequestException, ValueError) as error:
        logger.info("No se pudo chequear actualizaciones: %s", error)
        return resultado
