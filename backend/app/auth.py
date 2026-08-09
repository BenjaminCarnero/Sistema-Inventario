import bcrypt
import jwt
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.config import settings

# --- Protección contra fuerza bruta ---------------------------------------
# Los PIN de cajero son cortos por diseño (se tipean rápido en el celular), así
# que sin freno se prueban por completo en minutos. Se cuenta por usuario+IP en
# memoria: alcanza para un POS de un local y no agrega dependencias.
# Para varias instancias del backend habría que mover esto a Redis.
MAX_INTENTOS = 5
VENTANA_SEGUNDOS = 300      # los fallos se olvidan pasados 5 minutos
BLOQUEO_SEGUNDOS = 60       # cuánto dura el bloqueo al superar el máximo

_intentos: dict[str, list[float]] = {}


def _clave(usuario: str, ip: str) -> str:
    return f"{(usuario or '').lower()}|{ip}"


def _recientes(clave: str) -> list[float]:
    ahora = time.time()
    fallos = [t for t in _intentos.get(clave, []) if ahora - t < VENTANA_SEGUNDOS]
    if fallos:
        _intentos[clave] = fallos
    else:
        _intentos.pop(clave, None)
    return fallos


def segundos_de_bloqueo(usuario: str, ip: str) -> int:
    """Devuelve cuántos segundos falta esperar, o 0 si puede intentar."""
    fallos = _recientes(_clave(usuario, ip))
    if len(fallos) < MAX_INTENTOS:
        return 0
    restante = BLOQUEO_SEGUNDOS - (time.time() - fallos[-1])
    return max(0, int(restante) + 1)


def registrar_intento_fallido(usuario: str, ip: str) -> None:
    clave = _clave(usuario, ip)
    fallos = _recientes(clave)
    fallos.append(time.time())
    _intentos[clave] = fallos


def limpiar_intentos(usuario: str, ip: str) -> None:
    _intentos.pop(_clave(usuario, ip), None)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except (ValueError, TypeError):
        # Hash corrupto o con formato inesperado: se trata como credencial inválida
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
