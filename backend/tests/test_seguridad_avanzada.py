"""Batería de seguridad, por categoría de ataque.

No busca cubrir código sino romper el sistema: suplantar identidad, saltar
permisos, inyectar, y sobre todo mover plata de formas que el negocio no
autorizó. Cada test describe el ataque que intenta.
"""
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import models
from app.config import settings
from app.routers import pagos
from tests.conftest import cabecera, crear_usuario, token_de


def token_crudo(datos: dict, clave: str = None, algoritmo: str = "HS256") -> str:
    """Firma un token a mano, para simular a un atacante."""
    return jwt.encode(datos, clave or settings.SECRET_KEY, algorithm=algoritmo)


@pytest.fixture
def encargado(client, db):
    crear_usuario(db, "encargado", "clave123", models.RolEnum.ENCARGADO.value)
    return cabecera(token_de(client, "encargado", "clave123"))


# ---------------------------------------------------------------------------
# Suplantación de identidad
# ---------------------------------------------------------------------------

class TestFalsificacionDeToken:
    def test_token_firmado_con_otra_clave(self, client, admin):
        """Sin verificar la firma, cualquiera se declara administrador."""
        falso = token_crudo({"sub": "admin", "rol": 1}, clave="la-clave-del-atacante")
        assert client.get("/reportes/kpi", headers=cabecera(falso)).status_code == 401

    def test_token_sin_firma(self, client, admin):
        """El clásico alg=none: token legible, sin firma que validar."""
        sin_firma = jwt.encode({"sub": "admin", "rol": 1}, key="", algorithm="none")
        assert client.get("/reportes/kpi", headers=cabecera(sin_firma)).status_code == 401

    def test_token_vencido(self, client, admin):
        vencido = token_crudo({
            "sub": "admin", "rol": 1,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        })
        assert client.get("/reportes/kpi", headers=cabecera(vencido)).status_code == 401

    def test_token_de_un_usuario_inexistente(self, client, admin):
        fantasma = token_crudo({
            "sub": "no-existe", "rol": 1,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        assert client.get("/reportes/kpi", headers=cabecera(fantasma)).status_code == 401

    def test_el_rol_del_token_no_manda(self, client, cajero, admin):
        """Un cajero que se firma un token diciendo que es admin.

        El rol tiene que salir de la base y no del token; si no, cualquiera que
        entienda cómo funciona un JWT se asciende solo.
        """
        mentiroso = token_crudo({
            "sub": "cajero", "rol": models.RolEnum.ADMIN.value,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        assert client.get("/reportes/kpi", headers=cabecera(mentiroso)).status_code == 403

    def test_la_sesion_muere_al_dar_de_baja_al_usuario(self, client, db, admin, auth_admin):
        """Si a un cajero le roban el celular, dar de baja tiene que cortar ya."""
        crear_usuario(db, "temporal", "clave123", models.RolEnum.CAJERO.value)
        auth = cabecera(token_de(client, "temporal", "clave123"))
        assert client.get("/productos/", headers=auth).status_code == 200

        usuario = db.query(models.Usuario).filter(models.Usuario.nombre == "temporal").first()
        usuario.estado = False
        db.commit()

        assert client.get("/productos/", headers=auth).status_code in (400, 401, 403)

    @pytest.mark.parametrize("cabecera_mala", [
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "no-es-un-esquema xyz"},
        {"Authorization": "Bearer a.b.c"},
        {"Authorization": "Bearer " + "A" * 5000},
    ])
    def test_cabeceras_malformadas_no_rompen_el_servidor(self, client, admin, cabecera_mala):
        respuesta = client.get("/productos/", headers=cabecera_mala)
        assert respuesta.status_code in (401, 403), respuesta.text


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

class TestPermisos:
    RUTAS_SOLO_ADMIN = ["/auditoria/", "/respaldos/"]
    RUTAS_DE_GESTION = [
        "/reportes/kpi", "/reportes/cajas", "/reportes/rentabilidad",
        "/proveedores/", "/pedidos/", "/pedidos/reponer", "/stock/movimientos",
    ]

    @pytest.mark.parametrize("ruta", RUTAS_SOLO_ADMIN + RUTAS_DE_GESTION)
    def test_el_cajero_no_entra_a_la_gestion(self, client, auth_cajero, admin, ruta):
        assert client.get(ruta, headers=auth_cajero).status_code == 403, ruta

    @pytest.mark.parametrize("ruta", RUTAS_SOLO_ADMIN)
    def test_el_encargado_no_ve_lo_que_lo_controla(self, client, encargado, admin, ruta):
        """La auditoría y las copias de la base son sólo del administrador."""
        assert client.get(ruta, headers=encargado).status_code == 403, ruta

    def test_sin_token_no_se_entra_a_ningun_lado(self, client, admin):
        for ruta in self.RUTAS_SOLO_ADMIN + self.RUTAS_DE_GESTION + ["/productos/", "/ventas/"]:
            assert client.get(ruta).status_code == 401, ruta

    def test_un_cajero_no_cierra_la_caja_de_otro(self, client, db, admin, auth_admin):
        """Cerrar la caja ajena permitiría tapar un faltante propio."""
        caja = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 1000}).json()

        crear_usuario(db, "otro", "clave123", models.RolEnum.CAJERO.value)
        ajeno = cabecera(token_de(client, "otro", "clave123"))

        r = client.put(f"/cajas/{caja['id']}/cerrar", headers=ajeno, json={"monto_final_declarado": 1000})
        assert r.status_code == 404

    def test_el_cajero_solo_ve_sus_propias_ventas(self, client, db, admin, auth_admin, producto, sin_iva):
        client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        crear_usuario(db, "curioso", "clave123", models.RolEnum.CAJERO.value)
        auth = cabecera(token_de(client, "curioso", "clave123"))
        assert client.get("/ventas/", headers=auth).json() == []


# ---------------------------------------------------------------------------
# Fuga de información
# ---------------------------------------------------------------------------

class TestFugaDeInformacion:
    def test_el_cajero_no_ve_el_costo_de_los_productos(self, client, auth_cajero, admin, producto):
        """El costo es el margen del negocio.

        El equipo del cajero descarta el costo antes de guardarlo, justamente
        para que no quede ahí; si la API lo entrega igual, esa precaución no
        sirve de nada.
        """
        catalogo = client.get("/productos/", headers=auth_cajero).json()
        assert "costo" not in catalogo[0] or catalogo[0]["costo"] is None

    def test_el_admin_si_ve_el_costo(self, client, auth_admin, producto):
        catalogo = client.get("/productos/", headers=auth_admin).json()
        assert catalogo[0]["costo"] == 600.0

    def test_ninguna_respuesta_devuelve_el_pin(self, client, auth_admin, admin):
        cuerpo = client.get("/auth/users", headers=auth_admin).text
        assert "pin_acceso" not in cuerpo
        assert "$2b$" not in cuerpo  # el prefijo de un hash bcrypt

    def test_el_error_no_cuenta_si_el_usuario_existe(self, client, admin):
        inexistente = client.post("/auth/login", data={"username": "nadie", "password": "x"})
        existente = client.post("/auth/login", data={"username": "admin", "password": "mal"})
        assert inexistente.json() == existente.json()
        assert inexistente.status_code == existente.status_code

    def test_un_error_interno_no_muestra_las_entrañas(self, client, auth_admin):
        r = client.get("/reportes/ventas_periodo?desde=no-es-fecha&hasta=tampoco", headers=auth_admin)
        cuerpo = r.text.lower()
        for filtracion in ("traceback", "sqlalchemy", "select ", "site-packages", "app\\routers"):
            assert filtracion not in cuerpo, filtracion


# ---------------------------------------------------------------------------
# Inyección
# ---------------------------------------------------------------------------

PAYLOADS_SQL = [
    "' OR '1'='1",
    "'; DROP TABLE ventas;--",
    "1' UNION SELECT null,null,null--",
    "admin'--",
    "\\'; DELETE FROM productos WHERE '1'='1",
]


class TestInyeccionSQL:
    @pytest.mark.parametrize("payload", PAYLOADS_SQL)
    def test_no_se_saltea_el_login(self, client, admin, payload):
        r = client.post("/auth/login", data={"username": payload, "password": payload})
        assert r.status_code in (401, 429)

    @pytest.mark.parametrize("payload", PAYLOADS_SQL)
    def test_los_filtros_no_ejecutan_sql(self, client, auth_admin, producto, payload):
        client.get(f"/stock/movimientos?tipo={payload}", headers=auth_admin)
        client.get(f"/auditoria/?entidad={payload}", headers=auth_admin)
        client.get(f"/pedidos/?estado={payload}", headers=auth_admin)
        # Lo que importa es que la base siga entera después de todo eso
        assert client.get("/productos/", headers=auth_admin).status_code == 200

    def test_las_tablas_siguen_existiendo(self, client, auth_admin, producto, db):
        for payload in PAYLOADS_SQL:
            client.get(f"/productos/?skip=0&limit={payload}", headers=auth_admin)
        assert db.query(models.Producto).count() >= 1
        assert db.query(models.Venta).count() >= 0


class TestPathTraversal:
    @pytest.mark.parametrize("nombre", [
        "../.env",
        "../../backend/.env",
        "applify_/../../.env.db",
        "..%2F..%2F.env",
        "%2e%2e%2f.env",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "applify_%00.db",
        "applify_....//....//.env.db",
    ])
    def test_no_se_baja_cualquier_archivo(self, client, auth_admin, nombre):
        """El nombre del respaldo llega por la red: sin control es un lector de archivos."""
        r = client.get(f"/respaldos/{nombre}", headers=auth_admin)
        assert r.status_code in (400, 404, 422), f"{nombre} -> {r.status_code}"


class TestContenidoPeligroso:
    @pytest.mark.parametrize("payload", [
        "<script>alert(1)</script>",
        "javascript:alert(1)",
        "<img src=x onerror=alert(1)>",
        "{{7*7}}",
    ])
    def test_se_guarda_como_texto_y_no_se_interpreta(self, client, auth_admin, payload):
        r = client.post("/productos/", headers=auth_admin, json={
            "codigo_barras": f"xss-{abs(hash(payload))}", "nombre": payload,
            "precio_venta": 10, "costo": 5, "stock_actual": 1,
        })
        assert r.status_code == 201
        # La respuesta es JSON: el navegador no la ejecuta como HTML
        assert r.headers["content-type"].startswith("application/json")
        assert r.json()["nombre"] == payload

    def test_la_imagen_no_acepta_esquemas_ejecutables(self, client, auth_admin):
        for esquema in ("javascript:alert(1)", "vbscript:msgbox", "file:///etc/passwd", "data:text/html,<script>"):
            r = client.post("/productos/", headers=auth_admin, json={
                "codigo_barras": f"img-{abs(hash(esquema))}", "nombre": "x",
                "precio_venta": 10, "costo": 5, "stock_actual": 1, "imagen_url": esquema,
            })
            assert r.status_code == 400, esquema


# ---------------------------------------------------------------------------
# Asignación masiva
# ---------------------------------------------------------------------------

class TestAsignacionMasiva:
    def test_el_cliente_no_elige_de_quien_es_la_venta(self, client, auth_cajero, admin, producto, sin_iva, db):
        """Atribuirle la venta a otro cajero ensuciaría su arqueo."""
        r = client.post("/ventas/", headers=auth_cajero, json={
            "usuario_id": admin.id,
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        assert r.status_code == 201
        venta = db.query(models.Venta).filter(models.Venta.id == r.json()["id"]).first()
        assert venta.usuario_id != admin.id

    def test_el_cliente_no_fija_el_total(self, client, auth_admin, producto, sin_iva):
        r = client.post("/ventas/", headers=auth_admin, json={
            "total": 1,
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 2, "precio_unitario": 1000}],
        })
        assert r.json()["total"] == 2000.0

    def test_el_cliente_no_declara_la_venta_anulada(self, client, auth_admin, producto, sin_iva, db):
        """Nacer anulada sacaría la venta de los reportes sin devolver nada."""
        r = client.post("/ventas/", headers=auth_admin, json={
            "estado": "ANULADA",
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        venta = db.query(models.Venta).filter(models.Venta.id == r.json()["id"]).first()
        assert venta.estado == "COMPLETADA"

    def test_el_cliente_no_pone_la_fecha(self, client, auth_admin, producto, sin_iva, db):
        """Fechar una venta en el pasado la sacaría del arqueo del turno."""
        r = client.post("/ventas/", headers=auth_admin, json={
            "fecha_hora": "2020-01-01T00:00:00",
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        venta = db.query(models.Venta).filter(models.Venta.id == r.json()["id"]).first()
        assert venta.fecha_hora.year >= 2024


# ---------------------------------------------------------------------------
# Lógica de negocio: la plata
# ---------------------------------------------------------------------------

class TestManipulacionDePrecios:
    def test_el_precio_lo_pone_el_servidor(self, client, auth_cajero, admin, producto, sin_iva):
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1}],
        })
        assert r.json()["total"] == 1000.0

    def test_no_se_vende_con_precio_negativo(self, client, auth_cajero, admin, producto):
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": -1000}],
        })
        assert r.status_code == 422

    @pytest.mark.parametrize("cantidad", [0, -1, -9999])
    def test_no_se_vende_una_cantidad_no_positiva(self, client, auth_cajero, admin, producto, cantidad):
        """Una cantidad negativa devolvería stock y restaría del total."""
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": cantidad, "precio_unitario": 1000}],
        })
        assert r.status_code == 422

    def test_no_se_crea_un_producto_con_precio_negativo(self, client, auth_admin):
        r = client.post("/productos/", headers=auth_admin, json={
            "codigo_barras": "neg", "nombre": "x", "precio_venta": -1, "costo": 1, "stock_actual": 1,
        })
        assert r.status_code == 400

    def test_por_defecto_se_puede_vender_sin_stock(self, client, auth_cajero, admin, producto, sin_iva):
        """Es a propósito: el cajero ya tiene el producto en la mano.

        Frenar la venta porque el conteo está mal es peor que dejar el stock en
        negativo, que además queda a la vista para corregirlo.
        """
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 101, "precio_unitario": 1000}],
        })
        assert r.status_code == 201

    def test_con_el_control_activado_no_se_vende_de_mas(self, client, auth_admin, auth_cajero, producto, sin_iva):
        """Y si el comercio prefiere frenar, el control tiene que funcionar."""
        client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"permitir_stock_negativo": False},
        })
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 101, "precio_unitario": 1000}],
        })
        assert r.status_code == 400

    def test_el_control_no_se_saltea_partiendo_la_venta_en_lineas(self, client, auth_admin, auth_cajero, producto, sin_iva):
        """Cien líneas de dos unidades no pueden pasar donde una de 200 no pasa."""
        client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"permitir_stock_negativo": False},
        })
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 2, "precio_unitario": 1000}] * 100,
        })
        assert r.status_code == 400


class TestAbusoDeDescuentos:
    def _descuento(self, client, auth, **kwargs):
        datos = {"nombre": "promo", "tipo": "PORCENTAJE", "valor": 10, "activo": True}
        datos.update(kwargs)
        return client.post("/descuentos/", headers=auth, json=datos)

    def test_no_se_descuenta_mas_del_cien_por_ciento(self, client, auth_admin):
        assert self._descuento(client, auth_admin, valor=150).status_code == 400

    def test_no_se_descuenta_un_valor_negativo(self, client, auth_admin):
        """Un descuento negativo sería un recargo silencioso."""
        assert self._descuento(client, auth_admin, valor=-50).status_code == 400

    def test_la_venta_nunca_termina_en_negativo(self, client, auth_admin, producto, sin_iva):
        descuento = self._descuento(client, auth_admin, tipo="MONTO", valor=999999).json()
        r = client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO", "descuento_id": descuento["id"],
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        if r.status_code == 201:
            assert r.json()["total"] >= 0

    def test_un_descuento_inexistente_no_pasa(self, client, auth_admin, producto, sin_iva):
        r = client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO", "descuento_id": 999999,
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        assert r.status_code in (400, 404)


class TestAbusoDeDevoluciones:
    def _vender(self, client, auth, producto, cantidad=3):
        return client.post("/ventas/", headers=auth, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": cantidad, "precio_unitario": 1000}],
        }).json()

    def test_no_se_devuelve_mas_de_lo_vendido(self, client, auth_admin, producto, sin_iva):
        venta = self._vender(client, auth_admin, producto)
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 99}],
        })
        assert r.status_code == 400

    def test_no_se_devuelve_una_cantidad_negativa(self, client, auth_admin, producto, sin_iva):
        """Una cantidad negativa restaría stock y sumaría plata a la caja."""
        venta = self._vender(client, auth_admin, producto)
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": -5}],
        })
        assert r.status_code == 422

    def test_no_se_devuelve_dos_veces_lo_mismo(self, client, auth_admin, producto, sin_iva, db):
        venta = self._vender(client, auth_admin, producto)
        for _ in range(2):
            client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
                "detalles": [{"producto_id": producto.id, "cantidad": 3}],
            })
        devuelto = db.query(models.DetalleDevolucion).all()
        assert sum(d.cantidad for d in devuelto) <= 3

    def test_no_se_devuelve_un_producto_de_otra_venta(self, client, auth_admin, producto, sin_iva, db):
        otro = models.Producto(codigo_barras="otro", nombre="Otro", precio_venta=5000,
                               costo=1, stock_actual=10)
        db.add(otro)
        db.commit()
        db.refresh(otro)

        venta = self._vender(client, auth_admin, producto)
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": otro.id, "cantidad": 1}],
        })
        assert r.status_code == 400


class TestIdempotencia:
    def test_reintentar_no_duplica_la_venta(self, client, auth_cajero, admin, producto, sin_iva, db):
        cuerpo = {
            "metodo_pago": "EFECTIVO", "uuid_cliente": "el-mismo-uuid",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }
        primera = client.post("/ventas/", headers=auth_cajero, json=cuerpo).json()
        segunda = client.post("/ventas/", headers=auth_cajero, json=cuerpo).json()

        assert primera["id"] == segunda["id"]
        assert db.query(models.Venta).count() == 1

    def test_reusar_el_uuid_con_otro_contenido_no_cobra_de_nuevo(self, client, auth_cajero, admin, producto, sin_iva, db):
        """Con el mismo identificador, el segundo pedido no puede vender más."""
        client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO", "uuid_cliente": "repetido",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        db.refresh(producto)
        stock = producto.stock_actual

        client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO", "uuid_cliente": "repetido",
            "detalles": [{"producto_id": producto.id, "cantidad": 50, "precio_unitario": 1000}],
        })
        db.refresh(producto)
        assert producto.stock_actual == stock


class TestCambioDePin:
    """Sin esto, un PIN visto por encima del hombro sólo se sacaba de
    circulación borrando la cuenta, lo que le cambia el id y desengancha del
    historial las ventas de esa persona."""

    def test_el_cajero_cambia_el_suyo_y_entra_con_el_nuevo(self, client, auth_cajero, cajero):
        r = client.put("/auth/me/pin", headers=auth_cajero, json={
            "pin_actual": "cajero123", "pin_nuevo": "9876",
        })
        assert r.status_code == 204, r.text

        assert client.post("/auth/login", data={"username": "cajero", "password": "cajero123"}).status_code == 401
        assert client.post("/auth/login", data={"username": "cajero", "password": "9876"}).status_code == 200

    def test_hace_falta_saber_el_actual(self, client, auth_cajero, cajero):
        """Un equipo dejado abierto no puede alcanzar para quedarse la cuenta."""
        r = client.put("/auth/me/pin", headers=auth_cajero, json={
            "pin_actual": "el-que-no-es", "pin_nuevo": "9876",
        })
        assert r.status_code == 400
        assert client.post("/auth/login", data={"username": "cajero", "password": "cajero123"}).status_code == 200

    def test_el_nuevo_respeta_el_largo_del_rol(self, client, auth_admin, admin):
        r = client.put("/auth/me/pin", headers=auth_admin, json={
            "pin_actual": "admin123", "pin_nuevo": "1234",
        })
        assert r.status_code == 400

    def test_no_se_puede_poner_el_mismo(self, client, auth_cajero, cajero):
        r = client.put("/auth/me/pin", headers=auth_cajero, json={
            "pin_actual": "cajero123", "pin_nuevo": "cajero123",
        })
        assert r.status_code == 400

    def test_el_admin_le_reinicia_el_pin_al_que_se_lo_olvido(self, client, auth_admin, cajero):
        r = client.put(f"/auth/users/{cajero.id}/pin", headers=auth_admin, json={"pin_nuevo": "4321"})
        assert r.status_code == 204, r.text
        assert client.post("/auth/login", data={"username": "cajero", "password": "4321"}).status_code == 200

    def test_reiniciar_el_pin_destraba_la_cuenta_frenada(self, client, auth_admin, cajero):
        """Si arrastraba fallos, quedaría bloqueado justo con el PIN nuevo."""
        for _ in range(6):
            client.post("/auth/login", data={"username": "cajero", "password": "mal"})
        assert client.post("/auth/login", data={"username": "cajero", "password": "cajero123"}).status_code == 429

        client.put(f"/auth/users/{cajero.id}/pin", headers=auth_admin, json={"pin_nuevo": "4321"})
        assert client.post("/auth/login", data={"username": "cajero", "password": "4321"}).status_code == 200

    def test_un_cajero_no_le_cambia_el_pin_a_otro(self, client, auth_cajero, admin):
        r = client.put(f"/auth/users/{admin.id}/pin", headers=auth_cajero, json={"pin_nuevo": "loquesea99"})
        assert r.status_code == 403

    def test_el_pin_nunca_queda_en_la_auditoria(self, client, auth_cajero, cajero, db):
        client.put("/auth/me/pin", headers=auth_cajero, json={
            "pin_actual": "cajero123", "pin_nuevo": "secreto-9876",
        })
        entradas = db.query(models.Auditoria).all()
        assert entradas, "el cambio de PIN tiene que quedar registrado"
        for entrada in entradas:
            assert "secreto-9876" not in f"{entrada.valor_anterior}{entrada.valor_nuevo}"


class TestStockConcurrente:
    def test_el_mismo_producto_en_dos_lineas_no_esquiva_el_control_de_stock(
        self, client, auth_cajero, producto, sin_iva, db
    ):
        """La resta la hace la base, así que el objeto en memoria queda viejo:
        sin llevar la cuenta aparte, la segunda línea se validaba contra el
        stock inicial y el control se saltaba solo."""
        db.add(models.Configuracion(
            clave="permitir_stock_negativo", valor="false", tipo="boolean", categoria="ventas",
        ))
        producto.stock_actual = 3
        db.commit()

        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [
                {"producto_id": producto.id, "cantidad": 2, "precio_unitario": 1000},
                {"producto_id": producto.id, "cantidad": 2, "precio_unitario": 1000},
            ],
        })
        assert r.status_code == 400
        db.refresh(producto)
        assert producto.stock_actual == 3

    def test_el_mismo_producto_repetido_descuenta_todo(
        self, client, auth_cajero, producto, sin_iva, db
    ):
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [
                {"producto_id": producto.id, "cantidad": 2, "precio_unitario": 1000},
                {"producto_id": producto.id, "cantidad": 3, "precio_unitario": 1000},
            ],
        })
        assert r.status_code == 201, r.text
        assert r.json()["total"] == 5000
        db.refresh(producto)
        assert producto.stock_actual == 95


class TestCobroPorQR:
    """El cajero declara el pago; el servidor lo comprueba.

    Antes alcanzaba con mandar `metodo_pago=MERCADOPAGO` para que la venta
    quedara registrada como cobrada, el stock bajara y el arqueo la contara,
    sin que hubiera entrado un peso ni quedara nada que conciliar.
    """

    def _vender_qr(self, client, auth, producto, **extra):
        cuerpo = {
            "metodo_pago": "MERCADOPAGO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }
        cuerpo.update(extra)
        return client.post("/ventas/", headers=auth, json=cuerpo)

    def _acreditar(self, monkeypatch, monto: float):
        monkeypatch.setattr(pagos, "total_aprobado", lambda referencia: monto)

    def test_sin_referencia_del_cobro_no_hay_venta(self, client, auth_cajero, producto, sin_iva, db):
        r = self._vender_qr(client, auth_cajero, producto)
        assert r.status_code == 400
        db.refresh(producto)
        assert producto.stock_actual == 100

    def test_declarar_el_pago_sin_que_exista_no_alcanza(self, client, auth_cajero, producto, sin_iva, db, monkeypatch):
        self._acreditar(monkeypatch, 0.0)
        r = self._vender_qr(client, auth_cajero, producto, pago_referencia="ref-sin-pago")
        assert r.status_code == 402
        # El rollback tiene que devolver el stock que se descontó antes de comprobar
        db.refresh(producto)
        assert producto.stock_actual == 100
        assert db.query(models.Venta).count() == 0

    def test_pagar_de_menos_no_cierra_la_venta(self, client, auth_cajero, producto, sin_iva, db, monkeypatch):
        """Una preferencia de $1 no puede dar por cobrado un carrito de $1000."""
        self._acreditar(monkeypatch, 1.0)
        r = self._vender_qr(client, auth_cajero, producto, pago_referencia="ref-de-un-peso")
        assert r.status_code == 402
        db.refresh(producto)
        assert producto.stock_actual == 100

    def test_con_el_cobro_acreditado_la_venta_entra(self, client, auth_cajero, producto, sin_iva, db, monkeypatch):
        self._acreditar(monkeypatch, 1000.0)
        r = self._vender_qr(client, auth_cajero, producto, pago_referencia="ref-buena")
        assert r.status_code == 201, r.text
        # La referencia queda guardada: es lo que después permite conciliar
        assert r.json()["pago_referencia"] == "ref-buena"
        db.refresh(producto)
        assert producto.stock_actual == 99

    def test_un_mismo_cobro_no_paga_dos_ventas(self, client, auth_cajero, producto, sin_iva, monkeypatch):
        self._acreditar(monkeypatch, 1000.0)
        primera = self._vender_qr(client, auth_cajero, producto, pago_referencia="ref-unica")
        assert primera.status_code == 201

        segunda = self._vender_qr(client, auth_cajero, producto, pago_referencia="ref-unica")
        assert segunda.status_code == 409

    def test_el_total_lo_pone_el_servidor_no_el_cliente(self, client, auth_cajero, producto, sin_iva, monkeypatch):
        """El cliente pide 3 unidades ($3000) declarando un precio de $1: lo que
        se compara contra Mercado Pago es el total del catálogo, no el suyo."""
        self._acreditar(monkeypatch, 3.0)
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "MERCADOPAGO",
            "pago_referencia": "ref-barata",
            "detalles": [{"producto_id": producto.id, "cantidad": 3, "precio_unitario": 1}],
        })
        assert r.status_code == 402


class TestCaja:
    def test_no_se_abre_con_un_monto_negativo(self, client, auth_admin):
        assert client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": -5000}).status_code == 400

    def test_no_se_abre_con_un_monto_absurdo(self, client, auth_admin):
        assert client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 10**12}).status_code == 400

    def test_no_se_cierra_dos_veces(self, client, auth_admin):
        caja = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 1000}).json()
        client.put(f"/cajas/{caja['id']}/cerrar", headers=auth_admin, json={"monto_final_declarado": 1000})
        r = client.put(f"/cajas/{caja['id']}/cerrar", headers=auth_admin, json={"monto_final_declarado": 999999})
        assert r.status_code in (400, 404)


# ---------------------------------------------------------------------------
# Denegación de servicio y límites
# ---------------------------------------------------------------------------

class TestLimites:
    def test_el_bloqueo_no_se_evita_cambiando_mayusculas(self, client, admin):
        """Si la clave distinguiera mayúsculas, ADMIN sería otro casillero."""
        for _ in range(5):
            client.post("/auth/login", data={"username": "admin", "password": "mal"})
        r = client.post("/auth/login", data={"username": "ADMIN", "password": "mal"})
        assert r.status_code == 429

    def test_un_cuerpo_gigante_se_rechaza(self, client, auth_admin, producto):
        enorme = {
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1}] * 60_000,
        }
        assert client.post("/ventas/", json=enorme, headers=auth_admin).status_code == 413

    def test_demasiadas_lineas_en_una_venta(self, client, auth_admin, producto, sin_iva):
        r = client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}] * 500,
        })
        assert r.status_code == 400

    def test_los_textos_larguisimos_se_rechazan(self, client, auth_admin, producto, sin_iva):
        venta = client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "motivo": "A" * 10_000, "detalles": [{"producto_id": producto.id, "cantidad": 1}],
        })
        assert r.status_code == 422

    def test_un_json_muy_anidado_no_tumba_el_servidor(self, client, auth_admin):
        anidado = {"valores": {}}
        actual = anidado["valores"]
        for _ in range(200):
            actual["a"] = {}
            actual = actual["a"]
        r = client.put("/configuracion/", headers=auth_admin, json=anidado)
        assert r.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Criptografía y cabeceras
# ---------------------------------------------------------------------------

class TestGuardadoDeClaves:
    def test_dos_pines_iguales_dan_hashes_distintos(self, db):
        """Sin sal, una tabla de hashes revela a todos los que usan el mismo PIN."""
        from app import auth as modulo_auth
        assert modulo_auth.get_password_hash("1234") != modulo_auth.get_password_hash("1234")

    def test_el_pin_no_se_guarda_en_claro(self, db, client, auth_admin):
        client.post("/auth/register", headers=auth_admin, json={
            "nombre": "nuevo", "pin_acceso": "clave-secreta", "rol_id": 3, "estado": True,
        })
        usuario = db.query(models.Usuario).filter(models.Usuario.nombre == "nuevo").first()
        assert usuario.pin_acceso != "clave-secreta"
        assert usuario.pin_acceso.startswith("$2")  # bcrypt


class TestCabeceras:
    def test_estan_las_cabeceras_de_seguridad(self, client):
        c = client.get("/health").headers
        assert c["X-Frame-Options"] == "DENY"
        assert c["X-Content-Type-Options"] == "nosniff"
        assert "frame-ancestors 'none'" in c["Content-Security-Policy"]
        assert c.get("Referrer-Policy")

    def test_no_se_anuncia_la_version_del_servidor(self, client):
        """Saber la versión exacta le ahorra trabajo a quien busca un exploit."""
        servidor = client.get("/health").headers.get("server", "")
        assert "/" not in servidor, f"anuncia versión: {servidor}"
