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


# Más de esto sin una copia fuera del disco es una alarma: con un respaldo
# por cierre de caja, un comercio que abre todos los días debería generar uno
# nuevo seguido. Fijo y no configurable a propósito, para no sumarle una
# opción más a una pantalla que ya tiene bastantes.
DIAS_DE_ALARMA_SIN_RESPALDO_EXTERNO = 2


def estado_externo() -> dict:
    """Hace cuánto hay una copia en `RESPALDO_EXTERNO`, si está configurado.

    Se mira la carpeta externa directamente en vez de guardar un registro
    aparte: `_copiar_afuera` ya deja ahí el mismo nombre de archivo que la
    copia local, así que la fecha del archivo más nuevo *es* la fecha del
    último respaldo externo que salió bien. Un registro aparte podría
    desincronizarse; leer la carpeta no puede mentir.
    """
    destino_externo = (settings.RESPALDO_EXTERNO or "").strip()
    resultado = {
        "configurado": bool(destino_externo),
        "alcanzable": False,
        "ultimo": None,
        "dias_desde_ultimo": None,
        "en_alarma": False,
    }
    if not destino_externo:
        # Sin destino configurado no hay "alarma": ya está claro en la
        # pantalla de Configuración que RESPALDO_EXTERNO está vacío, y avisar
        # dos veces de lo mismo no ayuda a nadie a arreglarlo.
        return resultado

    carpeta = Path(destino_externo)
    if not carpeta.exists():
        # Configurado pero inalcanzable (el pendrive no está puesto, la
        # carpeta de OneDrive no existe en esta cuenta) es tan grave como no
        # tener nada: las copias que se creyeron hechas nunca salieron de acá.
        resultado["en_alarma"] = True
        return resultado

    resultado["alcanzable"] = True
    copias = sorted(carpeta.glob(f"{PREFIJO}*{SUFIJO}"))
    if not copias:
        resultado["en_alarma"] = True
        return resultado

    ultimo_mtime = copias[-1].stat().st_mtime
    ultimo = datetime.fromtimestamp(ultimo_mtime)
    dias = (datetime.now() - ultimo).total_seconds() / 86400

    resultado["ultimo"] = ultimo
    resultado["dias_desde_ultimo"] = round(dias, 1)
    resultado["en_alarma"] = dias > DIAS_DE_ALARMA_SIN_RESPALDO_EXTERNO
    return resultado
