"""Copias de seguridad de la base.

El riesgo más probable de este sistema no es un atacante: es perder el archivo
de la base. Ahí se van el inventario, el historial de ventas y los arqueos.

La copia se hace con la API de respaldo de SQLite y no copiando el archivo con
el sistema operativo. Copiar el archivo mientras alguien está vendiendo puede
dejar una base a medio escribir, que es peor que no tener copia: parece que
está y no sirve.
"""
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from app.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

CARPETA = BASE_DIR / "respaldos"

# Cuántas copias externas se conservan. Menos que las locales: la carpeta
# externa suele ser un espacio sincronizado o un pendrive, con menos lugar.
MAXIMO_EXTERNO = 10

# Cuántas copias se conservan. Con una por cierre de caja, veinte cubren
# aproximadamente un mes de trabajo sin llenar el disco.
MAXIMO_A_CONSERVAR = 20

PREFIJO = "applify_"
SUFIJO = ".db"


def _ruta_de_la_base() -> Optional[Path]:
    """Ubicación del archivo SQLite, o None si la base no es SQLite."""
    url = settings.DATABASE_URL
    prefijo = "sqlite:///"
    if not url.startswith(prefijo):
        return None
    ruta = url[len(prefijo):]
    if not ruta or ruta == ":memory:":
        return None
    return Path(ruta)


def crear(motivo: str = "manual") -> Optional[Path]:
    """Guarda una copia consistente y devuelve su ruta.

    Devuelve None si la base no es un archivo SQLite (por ejemplo, SQL Server),
    donde las copias las maneja el propio motor.
    """
    origen = _ruta_de_la_base()
    if origen is None or not origen.exists():
        return None

    CARPETA.mkdir(parents=True, exist_ok=True)

    # El motivo va en el nombre para saber de un vistazo si la copia salió de
    # un cierre de caja o de alguien apretando el botón
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    limpio = "".join(c for c in motivo if c.isalnum() or c in "-_")[:20] or "manual"

    # Dos copias dentro del mismo segundo tendrían el mismo nombre y la segunda
    # pisaría a la primera. Pasa al cerrar dos cajas seguidas, o al apretar el
    # botón dos veces.
    destino = CARPETA / f"{PREFIJO}{marca}_{limpio}{SUFIJO}"
    repeticion = 1
    while destino.exists():
        repeticion += 1
        destino = CARPETA / f"{PREFIJO}{marca}_{limpio}_{repeticion}{SUFIJO}"

    conexion_origen = sqlite3.connect(str(origen))
    try:
        conexion_destino = sqlite3.connect(str(destino))
        try:
            # `backup` toma un punto consistente aunque haya escrituras en curso
            conexion_origen.backup(conexion_destino)
        finally:
            conexion_destino.close()
    finally:
        conexion_origen.close()

    _podar()
    _copiar_afuera(destino)
    return destino


def _copiar_afuera(copia: Path) -> Optional[Path]:
    """Deja una segunda copia fuera de este disco, si hay carpeta configurada.

    Va después de que la copia local quedó cerrada y nunca al revés: si la
    carpeta externa está caída —el pendrive no está puesto, la red se cortó—,
    el respaldo local igual quedó hecho. Por eso los errores se registran pero
    no se propagan: quedarse sin copia externa es malo, pero perder el cierre
    de caja por eso sería peor.
    """
    destino_externo = (settings.RESPALDO_EXTERNO or "").strip()
    if not destino_externo:
        return None

    try:
        carpeta = Path(destino_externo)
        carpeta.mkdir(parents=True, exist_ok=True)
        afuera = carpeta / copia.name
        shutil.copy2(copia, afuera)
        _podar_carpeta(carpeta, MAXIMO_EXTERNO)
        return afuera
    except OSError as error:
        logger.warning("No se pudo copiar el respaldo a %s: %s", destino_externo, error)
        return None


def _podar_carpeta(carpeta: Path, maximo: int) -> None:
    """Deja sólo las `maximo` copias más recientes de una carpeta."""
    copias = sorted(carpeta.glob(f"{PREFIJO}*{SUFIJO}"))
    for vieja in copias[:-maximo]:
        try:
            vieja.unlink()
        except OSError:
            pass  # que no se pueda borrar una vieja no invalida la nueva


def _podar() -> None:
    """Deja sólo las copias más recientes."""
    _podar_carpeta(CARPETA, MAXIMO_A_CONSERVAR)


def listar() -> List[dict]:
    """Copias disponibles, de la más reciente a la más vieja."""
    if not CARPETA.exists():
        return []

    copias = []
    for archivo in sorted(CARPETA.glob(f"{PREFIJO}*{SUFIJO}"), reverse=True):
        info = archivo.stat()
        copias.append({
            "nombre": archivo.name,
            "bytes": info.st_size,
            "fecha_hora": datetime.fromtimestamp(info.st_mtime),
        })
    return copias


def ruta_de(nombre: str) -> Optional[Path]:
    """Ubica una copia por su nombre, sin dejar salir de la carpeta.

    El nombre llega desde la red: sin este chequeo, un nombre como
    "../.env" serviría para descargar cualquier archivo del servidor.
    """
    if not nombre.startswith(PREFIJO) or not nombre.endswith(SUFIJO):
        return None
    candidato = (CARPETA / nombre).resolve()
    if candidato.parent != CARPETA.resolve() or not candidato.exists():
        return None
    return candidato
