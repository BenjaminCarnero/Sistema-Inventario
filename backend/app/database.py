from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

_es_sqlite = settings.DATABASE_URL.startswith("sqlite")

# SQLite necesita desactivar el chequeo de hilo porque FastAPI atiende cada
# request en un hilo distinto del pool. Con SQL Server u otro motor no aplica.
connect_args = {"check_same_thread": False} if _es_sqlite else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


if _es_sqlite:
    @event.listens_for(engine, "connect")
    def _ajustar_sqlite(conexion, _registro):
        """Deja a SQLite usable con más de una caja a la vez.

        Con el journal por defecto, una escritura bloquea a toda la base: dos
        cajeros cobrando al mismo tiempo se traban y a los cinco segundos la
        venta muere con "database is locked". En WAL los lectores no molestan
        al que escribe, que es exactamente el patrón de un POS.

        `synchronous` se deja en FULL a propósito. WAL suele recomendarse con
        NORMAL por velocidad, pero ahí un corte de luz puede llevarse las
        últimas transacciones confirmadas: en un comercio el corte de luz es un
        martes cualquiera, y esas transacciones son ventas cobradas.
        """
        cursor = conexion.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            # Diez segundos esperando el lock antes de fallar, en vez de cinco.
            # Una venta que tarda un instante de más es mejor que una que se cae.
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Sesión por request: se cierra siempre, haya error o no."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
