"""Conversión entre el día del comercio y lo que hay guardado en la base.

Las fechas se guardan en UTC, pero un día para el comercio es el día de su
reloj de pared. Comparar una fecha local contra una columna en UTC parece
funcionar hasta que no: después de las 21:00 en Argentina las dos dejan de
coincidir, justo en el horario en que más se vende.

Esto vivía dentro de `reportes.py` y por eso el arreglo llegó sólo a los
reportes: el historial de stock y el registro de auditoría siguieron filtrando
con fechas naive un tiempo más. Está acá para que haya un solo lugar donde
mirar.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


def zona_del_comercio():
    """Zona horaria con la que se define "el día" del local.

    Sin `ZONA_HORARIA` en el .env se usa la del reloj del servidor, que es lo
    correcto cuando el servidor está en el mostrador. Deja de serlo apenas se
    hostea: un VPS en UTC corta el día a las 21:00 hora argentina, justo en el
    horario en que más se vende, y esas ventas caen en el reporte de mañana.
    """
    nombre = (settings.ZONA_HORARIA or "").strip()
    if not nombre:
        return None  # None = la del sistema, que es lo que hace astimezone()

    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        # No se aborta el arranque por esto: el sistema sigue andando con la
        # zona del servidor, que es el comportamiento de siempre.
        logger.warning(
            "ZONA_HORARIA='%s' no es una zona conocida: se usa la del servidor.", nombre
        )
        return None


def rango_local_en_utc(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """Convierte días del calendario del local a un rango en UTC.

    El rango es semiabierto (incluye `desde`, excluye el día siguiente a
    `hasta`) y permite usar el índice de la columna, en vez de calcular una
    función sobre cada fila.
    """
    zona = zona_del_comercio()
    inicio = datetime.combine(desde, time.min, tzinfo=zona) \
        .astimezone(timezone.utc).replace(tzinfo=None)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=zona) \
        .astimezone(timezone.utc).replace(tzinfo=None)
    return inicio, fin


def hoy_local() -> date:
    """Qué día es hoy para el comercio."""
    return datetime.now(zona_del_comercio() or None).date()


def dia_local_en_utc(dias_atras: int = 0) -> tuple[datetime, datetime]:
    """Rango en UTC del día local de hoy, o de hace tantos días."""
    dia = hoy_local() - timedelta(days=dias_atras)
    return rango_local_en_utc(dia, dia)


def fecha_local_de(momento_utc: datetime) -> date:
    """Con qué día del local se corresponde un instante guardado en UTC."""
    return momento_utc.replace(tzinfo=timezone.utc).astimezone(zona_del_comercio()).date()


def dia_desde_texto(texto: str) -> date:
    """Lee un "YYYY-MM-DD" recibido por la API."""
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="La fecha debe tener el formato YYYY-MM-DD")


def filtro_de_dias(desde: str | None, hasta: str | None) -> tuple[datetime | None, datetime | None]:
    """Convierte los parámetros `desde`/`hasta` de la API a límites en UTC.

    Devuelve (inicio, fin) donde cualquiera puede ser None si no se pidió. El
    fin ya incluye el día completo, así que se compara con `<`.
    """
    inicio = fin = None
    if desde:
        inicio, _ = rango_local_en_utc(dia_desde_texto(desde), dia_desde_texto(desde))
    if hasta:
        _, fin = rango_local_en_utc(dia_desde_texto(hasta), dia_desde_texto(hasta))
    return inicio, fin
