"""Empaqueta los logs del backend para poder bajarlos desde el navegador.

Hoy la única forma de ver un error es que alguien entre por escritorio remoto
a la PC del local y busque `backend/logs/backend.log` a mano — y el dueño de
un comercio no sabe qué es eso ni dónde vive. Con esto alcanza un clic desde
Configuración.
"""
import io
import zipfile
from pathlib import Path

from app.config import BASE_DIR

CARPETA = BASE_DIR / "logs"


def zip_de_logs() -> bytes:
    """Arma un .zip en memoria con todos los archivos de log que haya.

    `RotatingFileHandler` deja `backend.log` (el actual) y hasta
    `backend.log.1` .. `.5` (los rotados): se incluyen todos, porque el error
    que se busca pudo haber quedado en el archivo de ayer, no en el de hoy.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if CARPETA.exists():
            for archivo in sorted(CARPETA.glob("backend.log*")):
                if archivo.is_file():
                    zf.write(archivo, arcname=archivo.name)
    return buffer.getvalue()
