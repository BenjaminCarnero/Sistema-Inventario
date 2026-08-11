import bcrypt
import jwt
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.config import settings

# --- Protección contra fuerza bruta ---------------------------------------
# Los PIN de cajero son cortos por diseño (se tipean rápido en el celular), así
# que sin freno se prueban por completo en minutos.
#
# Los intentos se guardan en la base y no en memoria: antes, reiniciar el
# servidor borraba el contador, y en desarrollo el servidor se reinicia solo
# cada vez que se toca un archivo. Con esto el freno sobrevive al reinicio y
# vale para todos los procesos del backend, no para uno solo.
MAX_INTENTOS = 5
VENTANA_SEGUNDOS = 300      # los fallos se olvidan pasados 5 minutos
BLOQUEO_SEGUNDOS = 60       # cuánto dura el bloqueo al superar el máximo


def _clave(usuario: str, ip: str) -> str:
    return f"{(usuario or '').lower()}|{ip}"


def _fallos_recientes(db, clave: str):
    """Intentos dentro de la ventana, del más viejo al más nuevo."""
    from app import models

    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=VENTANA_SEGUNDOS)
    return db.query(models.IntentoLogin).filter(
        models.IntentoLogin.usuario == clave,
        models.IntentoLogin.fecha_hora >= limite,
    ).order_by(models.IntentoLogin.fecha_hora).all()


def segundos_de_bloqueo(db, usuario: str, ip: str) -> int:
    """Devuelve cuántos segundos falta esperar, o 0 si puede intentar."""
    fallos = _fallos_recientes(db, _clave(usuario, ip))
    if len(fallos) < MAX_INTENTOS:
        return 0

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    restante = BLOQUEO_SEGUNDOS - (ahora - fallos[-1].fecha_hora).total_seconds()
    return max(0, int(restante) + 1)


def registrar_intento_fallido(db, usuario: str, ip: str) -> None:
    from app import models

    db.add(models.IntentoLogin(usuario=_clave(usuario, ip)))

    # Se aprovecha el paso para tirar lo viejo, así la tabla no crece sin fin
    viejo = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    db.query(models.IntentoLogin).filter(models.IntentoLogin.fecha_hora < viejo).delete()
    db.commit()


def limpiar_intentos(db, usuario: str, ip: str) -> None:
    """Un acceso correcto borra el historial de fallos de ese usuario."""
    from app import models

    db.query(models.IntentoLogin).filter(
        models.IntentoLogin.usuario == _clave(usuario, ip)
    ).delete()
    db.commit()


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
