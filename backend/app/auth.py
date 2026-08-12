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

# Contar sólo por (usuario, IP) dejaba pasar el barrido: probar cuatro o cinco
# PIN contra cada cuenta del local, sin despertar nunca el contador de ninguna.
#
# El segundo freno cuenta **cuántas cuentas distintas** se intentaron desde esa
# IP, y no cuántos intentos hubo. La diferencia importa: contando intentos, un
# cajero que se equivoca quince veces con su propio PIN dejaría sin entrar a
# todo el local, y detrás de un router —donde todas las cajas comparten una
# sola salida a internet— alcanzaría con un mostrador con mala mañana para
# cerrar el sistema entero. Probar ocho cuentas distintas en cinco minutos, en
# cambio, no le pasa a nadie que esté trabajando.
MAX_CUENTAS_POR_IP = 8

# Prefijo de las filas que cuentan por IP. En `_limpiar` se quitan las barras
# del nombre de usuario, así ninguna cuenta puede fabricar una clave que se
# confunda con estas.
_MARCA_IP = "|ip|"


def _limpiar(usuario: str) -> str:
    return (usuario or "").replace("|", "").lower()


def _clave(usuario: str, ip: str) -> str:
    return f"{_limpiar(usuario)}|{ip}"


def _clave_ip(ip: str, usuario: str) -> str:
    return f"{_MARCA_IP}{ip}|{_limpiar(usuario)}"


def _prefijo_ip(ip: str) -> str:
    return f"{_MARCA_IP}{ip}|"


def _fallos_recientes(db, clave: str):
    """Intentos dentro de la ventana, del más viejo al más nuevo."""
    from app import models

    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=VENTANA_SEGUNDOS)
    return db.query(models.IntentoLogin).filter(
        models.IntentoLogin.usuario == clave,
        models.IntentoLogin.fecha_hora >= limite,
    ).order_by(models.IntentoLogin.fecha_hora).all()


def _bloqueo_de(db, clave: str, maximo: int) -> int:
    fallos = _fallos_recientes(db, clave)
    if len(fallos) < maximo:
        return 0

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    restante = BLOQUEO_SEGUNDOS - (ahora - fallos[-1].fecha_hora).total_seconds()
    return max(0, int(restante) + 1)


def _bloqueo_por_barrido(db, ip: str) -> int:
    """Bloqueo por probar demasiadas cuentas distintas desde la misma IP."""
    from app import models

    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=VENTANA_SEGUNDOS)
    filas = db.query(models.IntentoLogin).filter(
        models.IntentoLogin.usuario.startswith(_prefijo_ip(ip)),
        models.IntentoLogin.fecha_hora >= limite,
    ).order_by(models.IntentoLogin.fecha_hora).all()

    if len({fila.usuario for fila in filas}) <= MAX_CUENTAS_POR_IP:
        return 0

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    restante = BLOQUEO_SEGUNDOS - (ahora - filas[-1].fecha_hora).total_seconds()
    return max(0, int(restante) + 1)


def segundos_de_bloqueo(db, usuario: str, ip: str) -> int:
    """Devuelve cuántos segundos falta esperar, o 0 si puede intentar.

    Manda el más restrictivo de los dos frenos: el de la cuenta y el del
    barrido de cuentas desde una misma IP.
    """
    return max(
        _bloqueo_de(db, _clave(usuario, ip), MAX_INTENTOS),
        _bloqueo_por_barrido(db, ip),
    )


def registrar_intento_fallido(db, usuario: str, ip: str) -> None:
    from app import models

    db.add(models.IntentoLogin(usuario=_clave(usuario, ip)))
    db.add(models.IntentoLogin(usuario=_clave_ip(ip, usuario)))

    # Se aprovecha el paso para tirar lo viejo, así la tabla no crece sin fin
    viejo = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    db.query(models.IntentoLogin).filter(models.IntentoLogin.fecha_hora < viejo).delete()
    db.commit()


def limpiar_intentos_de_cuenta(db, usuario: str) -> None:
    """Borra los fallos de una cuenta, venga de la IP que venga.

    Se usa al reiniciarle el PIN a alguien: si arrastraba intentos fallidos,
    quedaría bloqueado justo con el PIN nuevo que le acaban de dar.
    """
    from app import models

    marca = f"{_limpiar(usuario)}|"
    db.query(models.IntentoLogin).filter(
        models.IntentoLogin.usuario.startswith(marca)
    ).delete(synchronize_session=False)


def limpiar_intentos(db, usuario: str, ip: str) -> None:
    """Un acceso correcto borra el historial de fallos de ese usuario.

    El contador de la IP no se toca a propósito: si se limpiara, a un atacante
    le bastaría entrar a una cuenta propia cada tantos intentos para poner el
    freno en cero y seguir probando contra las demás.
    """
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


# --- Largo mínimo del PIN, por rol ----------------------------------------
# El cajero teclea su PIN decenas de veces por turno y en un mostrador: cuatro
# dígitos es un compromiso razonable. El administrador cambia precios, borra
# usuarios y descarga la base entera, así que se le exige más.
#
# Vive acá y no en el router porque `seed_admin.py` también lo necesita: cuando
# la política estaba sólo en el router, el script de instalación dejaba crear
# el primer administrador —la cuenta más privilegiada de todas— con un PIN de
# cuatro caracteres.
PIN_MINIMO = 4


def pin_minimo(rol_id: int) -> int:
    from app.models import RolEnum

    return {
        RolEnum.ADMIN.value: 8,
        RolEnum.ENCARGADO.value: 6,
        RolEnum.CAJERO.value: 4,
    }.get(rol_id, PIN_MINIMO)


# Hash descartable, con el mismo costo que uno real. Se usa cuando el usuario
# no existe para que la respuesta tarde lo mismo que cuando sí existe: sin
# esto, el login contesta en 1 ms para un nombre inventado y en 200 ms para uno
# válido, y el mensaje genérico de "usuario o PIN incorrectos" no sirve de nada
# frente a un cronómetro.
_HASH_SENUELO = bcrypt.hashpw(b"no-existe", bcrypt.gensalt()).decode('utf-8')


def verificar_credencial(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verifica el PIN tardando lo mismo exista o no la cuenta."""
    if not hashed_password:
        verify_password(plain_password, _HASH_SENUELO)
        return False
    return verify_password(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
