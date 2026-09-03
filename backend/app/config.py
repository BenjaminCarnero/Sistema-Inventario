import secrets
import sys
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings

# Carpeta `backend/`. Todo lo que es del proyecto (el .env, la base SQLite) se
# ubica a partir de acá y no del directorio desde donde se ejecutó el comando:
# arrancar uvicorn desde la raíz del repo creaba una base vacía aparte.
BASE_DIR = Path(__file__).resolve().parent.parent

# Clave que en versiones viejas venía escrita en el código. Se deja en una
# lista negra para avisar si alguien la arrastra en su .env: al haber estado
# en el repositorio, cualquiera podría firmar tokens válidos con ella.
SECRET_KEY_COMPROMETIDA = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"

# Un solo archivo `VERSION` en la raíz del repo, leído acá y por
# `installer/setup.iss` al empaquetar. Sin un número de versión visible,
# soportar por teléfono a un comercio es adivinar qué tiene instalado.
try:
    VERSION = (BASE_DIR.parent / "VERSION").read_text(encoding="utf-8").strip()
except FileNotFoundError:
    VERSION = "desconocida"


class Settings(BaseSettings):
    PROJECT_NAME: str = "APPLIFY POS"
    # Por defecto SQLite local. Para SQL Server se cambia desde el .env.
    DATABASE_URL: str = "sqlite:///./applify.db"

    # Sin SECRET_KEY en el entorno se genera una al azar en cada arranque: es
    # seguro, aunque invalida las sesiones abiertas al reiniciar. En producción
    # hay que fijarla en el .env para que las sesiones sobrevivan.
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 horas: cubre un turno largo

    # El token de Mercado Pago es una credencial: va en el .env, nunca en el código.
    MERCADOPAGO_ACCESS_TOKEN: str = ""

    # A dónde vuelve el comprador después de pagar con el QR. En producción
    # tiene que ser la dirección pública del POS: apuntando a localhost, el
    # cliente termina en una página que sólo existe en la máquina de la caja.
    FRONTEND_URL: str = "http://localhost:5173"

    # Orígenes que pueden llamar a la API desde el navegador. El comodín "*"
    # junto con credenciales deja que cualquier web haga pedidos autenticados,
    # así que por defecto se listan sólo los de desarrollo.
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Segunda copia de cada respaldo, fuera de este disco. Una copia que vive
    # al lado de la base no protege del caso más probable, que es que ese disco
    # se rompa o que se pierda la computadora. Apuntala a una carpeta que ya se
    # sincronice sola (Drive, OneDrive) o a un pendrive que quede siempre puesto.
    RESPALDO_EXTERNO: str = ""

    # Carpeta del frontend ya compilado. Si existe, la sirve la misma
    # aplicación y el comercio queda en un solo contenedor y un solo puerto.
    # Vacío = se busca en ../frontend/dist, que es donde queda al compilar.
    FRONTEND_DIST: str = ""

    # Cuántos proxies propios hay delante de la aplicación (nginx, Caddy, el
    # balanceador del hosting). Con 0 la IP sale del socket, que es lo correcto
    # cuando la aplicación se expone directo.
    #
    # Importa porque el freno de fuerza bruta cuenta por IP: detrás de un proxy
    # sin configurar, TODAS las peticiones llegan con la IP del proxy, así que
    # el freno por barrido de cuentas bloquearía a todo el local y el freno por
    # cuenta se volvería inútil. Se cuenta desde la derecha de
    # `X-Forwarded-For` a propósito: el cliente puede inventar las entradas de
    # la izquierda, pero no las que agrega nuestro propio proxy.
    PROXIES_CONFIABLES: int = 0

    # Techo de peticiones por IP y por minuto, fuera del login (que tiene su
    # propio freno, más estricto y persistido). 0 lo desactiva.
    LIMITE_PETICIONES_POR_MINUTO: int = 300

    # Zona horaria del comercio, en formato IANA ("America/Argentina/Buenos_Aires").
    # Es la que define dónde empieza y termina "el día" para los arqueos y los
    # reportes. Vacío = la del reloj del servidor.
    #
    # Importa cuando el servidor no está en el local: un VPS en UTC corta el
    # día a las 21:00 hora argentina, así que las ventas de la noche caían en
    # el reporte del día siguiente y el arqueo del turno no cerraba.
    ZONA_HORARIA: str = ""

    ENTORNO: str = "desarrollo"  # "produccion" activa los chequeos estrictos

    class Config:
        env_file = str(BASE_DIR / ".env")


settings = Settings()


def _sqlite_absoluta(url: str) -> str:
    """Ancla una ruta SQLite relativa a `backend/`.

    Con `sqlite:///./applify.db` la base sale de donde se haya ejecutado el
    comando. Levantar el servidor desde otra carpeta abría una base nueva y
    vacía, con el catálogo y las ventas aparentemente perdidos.
    """
    prefijo = "sqlite:///"
    if not url.startswith(prefijo):
        return url
    ruta = url[len(prefijo):]
    if not ruta or ruta == ":memory:" or Path(ruta).is_absolute():
        return url
    return f"{prefijo}{(BASE_DIR / ruta).resolve()}"


settings.DATABASE_URL = _sqlite_absoluta(settings.DATABASE_URL)


def _avisar(mensaje: str, critico: bool = False):
    prefijo = "ERROR DE SEGURIDAD" if critico else "AVISO DE SEGURIDAD"
    print(f"[{prefijo}] {mensaje}", file=sys.stderr)


es_produccion = settings.ENTORNO.strip().lower() in (
    "produccion", "producción", "production", "prod"
)

# --- Validaciones de arranque --------------------------------------------
if not settings.SECRET_KEY:
    if es_produccion:
        raise RuntimeError(
            "Falta SECRET_KEY. Definila en el archivo .env antes de levantar en producción."
        )
    settings.SECRET_KEY = secrets.token_urlsafe(48)
    _avisar(
        "No hay SECRET_KEY configurada: se generó una temporal. "
        "Las sesiones se cierran al reiniciar el servidor. "
        "Definí SECRET_KEY en backend/.env para evitarlo."
    )
elif settings.SECRET_KEY == SECRET_KEY_COMPROMETIDA:
    mensaje = (
        "La SECRET_KEY en uso es la que venía en el código y está publicada en el "
        "historial de git: cualquiera puede firmar tokens válidos. Cambiala ya."
    )
    if es_produccion:
        raise RuntimeError(mensaje)
    _avisar(mensaje, critico=True)

if "*" in settings.CORS_ORIGINS:
    if es_produccion:
        raise RuntimeError(
            'CORS_ORIGINS no puede ser "*" en producción: permitiría que cualquier '
            "sitio haga pedidos autenticados en nombre de tus usuarios."
        )
    _avisar('CORS_ORIGINS está en "*": aceptable sólo en desarrollo.')

if not settings.MERCADOPAGO_ACCESS_TOKEN:
    _avisar("Sin MERCADOPAGO_ACCESS_TOKEN: los cobros por QR van a fallar.")

# Chequeo aparte y no encadenado al anterior: si fuera un `elif`, una instalación
# que todavía no configuró Mercado Pago nunca vería este aviso, y al agregar el
# token después sólo aparecería en el siguiente reinicio.
if es_produccion and "localhost" in settings.FRONTEND_URL:
    _avisar(
        "FRONTEND_URL apunta a localhost: después de pagar con QR, el cliente "
        "va a caer en una página que no existe. Definila en backend/.env.",
        critico=True,
    )
