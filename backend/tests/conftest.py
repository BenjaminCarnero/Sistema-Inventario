"""Infraestructura común de los tests.

Cada test corre contra una base SQLite temporal y descartable: nunca se toca
la base real del comercio.
"""
import os
import tempfile

import pytest

# La configuración se lee al importar la app, así que las variables de entorno
# tienen que estar puestas antes de cualquier import de `app`.
_fd, _ruta_db = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_ruta_db}"
os.environ["SECRET_KEY"] = "clave-solo-para-tests-no-usar-en-produccion"
os.environ["ENTORNO"] = "desarrollo"
os.environ["MERCADOPAGO_ACCESS_TOKEN"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="function")
def db():
    """Base limpia para cada test, para que no se pisen entre sí."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Los intentos fallidos ahora viven en la base, así que se van con el
    # drop_all de arriba: el test que agota los intentos ya no deja bloqueado
    # al usuario "admin" para los que corren después.

    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture
def client(db):
    return TestClient(app)


def crear_usuario(db, nombre: str, pin: str, rol: int) -> models.Usuario:
    usuario = models.Usuario(
        nombre=nombre,
        pin_acceso=auth.get_password_hash(pin),
        rol_id=rol,
        estado=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def token_de(client: TestClient, usuario: str, pin: str) -> str:
    respuesta = client.post("/auth/login", data={"username": usuario, "password": pin})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabecera(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(db):
    return crear_usuario(db, "admin", "admin123", models.RolEnum.ADMIN.value)


@pytest.fixture
def cajero(db):
    return crear_usuario(db, "cajero", "cajero123", models.RolEnum.CAJERO.value)


@pytest.fixture
def auth_admin(client, admin):
    return cabecera(token_de(client, "admin", "admin123"))


@pytest.fixture
def auth_cajero(client, cajero):
    return cabecera(token_de(client, "cajero", "cajero123"))


@pytest.fixture
def producto(db):
    """Producto de $1000 con costo $600 y 100 unidades."""
    p = models.Producto(
        codigo_barras="7790000000001",
        nombre="Producto de prueba",
        precio_venta=1000.0,
        costo=600.0,
        stock_actual=100,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def sin_iva(db):
    """Desactiva el IVA para que los tests de totales sean directos."""
    db.add(models.Configuracion(
        clave="iva_porcentaje", valor="0", tipo="number", categoria="impuestos",
    ))
    db.commit()
