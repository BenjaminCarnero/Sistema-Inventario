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
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException


def rango_local_en_utc(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """Convierte días del calendario del local a un rango en UTC.

    El rango es semiabierto (incluye `desde`, excluye el día siguiente a
    `hasta`) y permite usar el índice de la columna, en vez de calcular una
    función sobre cada fila.
    """
    inicio = datetime.combine(desde, time.min).astimezone(timezone.utc).replace(tzinfo=None)
    fin = (datetime.combine(hasta, time.min) + timedelta(days=1)) \
        .astimezone(timezone.utc).replace(tzinfo=None)
    return inicio, fin


def dia_local_en_utc(dias_atras: int = 0) -> tuple[datetime, datetime]:
    """Rango en UTC del día local de hoy, o de hace tantos días."""
    dia = date.today() - timedelta(days=dias_atras)
    return rango_local_en_utc(dia, dia)


def fecha_local_de(momento_utc: datetime) -> date:
    """Con qué día del local se corresponde un instante guardado en UTC."""
    return momento_utc.replace(tzinfo=timezone.utc).astimezone().date()


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
