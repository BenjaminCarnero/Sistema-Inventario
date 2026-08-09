from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# SQLite necesita desactivar el chequeo de hilo porque FastAPI atiende cada
# request en un hilo distinto del pool. Con SQL Server u otro motor no aplica.
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Sesión por request: se cierra siempre, haya error o no."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
