"""Los agujeros que se encontraron en la auditoría, convertidos en tests.

Cada uno se explotó de verdad contra la API antes de arreglarlo. Están acá
para que no vuelvan a abrirse sin que nadie se entere.
"""
from app import models
from tests.conftest import crear_usuario, token_de, cabecera


class TestAltaDeUsuarios:
    def test_no_se_puede_crear_un_admin_sin_autenticacion(self, client, admin):
        """Era una toma de control total del sistema con una sola petición."""
        r = client.post("/auth/register", json={
            "nombre": "atacante", "pin_acceso": "hackeado", "rol_id": 1, "estado": True,
        })
        assert r.status_code == 401

    def test_un_cajero_no_puede_crear_usuarios(self, client, admin, auth_cajero):
        r = client.post("/auth/register", headers=auth_cajero, json={
            "nombre": "otro", "pin_acceso": "1234", "rol_id": 1, "estado": True,
        })
        assert r.status_code == 403

    def test_el_primer_usuario_se_puede_crear_sin_token(self, client, db):
        """Excepción necesaria para poder inicializar una instalación nueva."""
        assert db.query(models.Usuario).count() == 0
        r = client.post("/auth/register", json={
            "nombre": "primero", "pin_acceso": "unaClaveLarga", "rol_id": 1, "estado": True,
        })
        assert r.status_code == 201

    def test_rechaza_pin_demasiado_corto(self, client, auth_admin):
        r = client.post("/auth/register", headers=auth_admin, json={
            "nombre": "x", "pin_acceso": "12", "rol_id": 3, "estado": True,
        })
        assert r.status_code == 400

    def test_rechaza_rol_inexistente(self, client, auth_admin):
        r = client.post("/auth/register", headers=auth_admin, json={
            "nombre": "x", "pin_acceso": "1234", "rol_id": 99, "estado": True,
        })
        assert r.status_code == 400


class TestLogin:
    def test_una_cuenta_dada_de_baja_no_entra(self, client, db):
        usuario = crear_usuario(db, "baja", "1234", models.RolEnum.CAJERO.value)
        usuario.estado = False
        db.commit()
        r = client.post("/auth/login", data={"username": "baja", "password": "1234"})
        assert r.status_code == 403

    def test_bloquea_tras_varios_intentos_fallidos(self, client, admin):
        for _ in range(5):
            client.post("/auth/login", data={"username": "admin", "password": "mal"})
        r = client.post("/auth/login", data={"username": "admin", "password": "mal"})
        assert r.status_code == 429

    def test_el_error_no_revela_si_el_usuario_existe(self, client, admin):
        inexistente = client.post("/auth/login", data={"username": "nadie", "password": "x"})
        existente = client.post("/auth/login", data={"username": "admin", "password": "mal"})
        assert inexistente.json()["detail"] == existente.json()["detail"]

    def test_sql_injection_no_saltea_el_login(self, client, admin):
        r = client.post("/auth/login", data={"username": "admin' OR '1'='1", "password": "x"})
        assert r.status_code == 401


class TestUltimoAdministrador:
    def test_no_se_puede_eliminar_al_ultimo_admin(self, client, auth_admin, admin):
        r = client.delete(f"/auth/users/{admin.id}", headers=auth_admin)
        assert r.status_code == 400

    def test_no_se_puede_degradar_al_ultimo_admin(self, client, auth_admin, admin):
        r = client.put(f"/auth/users/{admin.id}", headers=auth_admin, json={
            "nombre": "admin", "rol_id": 3, "estado": True,
        })
        assert r.status_code == 400

    def test_con_otro_admin_activo_si_se_puede(self, client, auth_admin, admin, db):
        otro = crear_usuario(db, "admin2", "12345", models.RolEnum.ADMIN.value)
        r = client.delete(f"/auth/users/{otro.id}", headers=auth_admin)
        assert r.status_code == 204


class TestPermisosPorRol:
    def test_el_cajero_no_accede_a_los_reportes(self, client, auth_cajero, admin):
        assert client.get("/reportes/kpi", headers=auth_cajero).status_code == 403

    def test_el_cajero_no_puede_cambiar_la_configuracion(self, client, auth_cajero, admin):
        r = client.put("/configuracion/", headers=auth_cajero, json={"valores": {"iva_porcentaje": 0}})
        assert r.status_code == 403

    def test_el_cajero_no_puede_mover_stock(self, client, auth_cajero, admin, producto):
        r = client.post("/stock/movimientos", headers=auth_cajero, json={
            "producto_id": producto.id, "cantidad": 10, "tipo_movimiento": "INGRESO",
        })
        assert r.status_code == 403

    def test_el_cajero_si_puede_vender(self, client, auth_cajero, admin, producto, sin_iva):
        r = client.post("/ventas/", headers=auth_cajero, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        assert r.status_code == 201


class TestValidacionDeDatos:
    def test_rechaza_imagen_con_esquema_peligroso(self, client, auth_admin):
        r = client.post("/productos/", headers=auth_admin, json={
            "codigo_barras": "111", "nombre": "x", "precio_venta": 1, "costo": 1,
            "stock_actual": 1, "imagen_url": "javascript:alert(1)",
        })
        assert r.status_code == 400

    def test_rechaza_precio_negativo(self, client, auth_admin):
        r = client.post("/productos/", headers=auth_admin, json={
            "codigo_barras": "222", "nombre": "x", "precio_venta": -5, "costo": 1, "stock_actual": 1,
        })
        assert r.status_code == 400

    def test_rechaza_iva_fuera_de_rango(self, client, auth_admin):
        r = client.put("/configuracion/", headers=auth_admin, json={"valores": {"iva_porcentaje": 150}})
        assert r.status_code == 400

    def test_rechaza_color_de_marca_invalido(self, client, auth_admin):
        r = client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"marca_color_primario": "rojo"},
        })
        assert r.status_code == 400

    def test_rechaza_quedarse_sin_metodos_de_pago(self, client, auth_admin):
        r = client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"metodos_pago_habilitados": []},
        })
        assert r.status_code == 400

    def test_rechaza_efectivo_por_encima_del_tope(self, client, auth_admin):
        r = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 999_999_999})
        assert r.status_code == 400


class TestCabeceras:
    def test_las_respuestas_traen_las_cabeceras_de_seguridad(self, client):
        cabeceras = client.get("/health").headers
        assert cabeceras["X-Frame-Options"] == "DENY"
        assert cabeceras["X-Content-Type-Options"] == "nosniff"
        assert "frame-ancestors 'none'" in cabeceras["Content-Security-Policy"]

    def test_rechaza_peticiones_gigantes(self, client, auth_admin, producto):
        """Un pedido de varios MB dejaba al servidor colgado."""
        enorme = {
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1}] * 60_000,
        }
        r = client.post("/ventas/", json=enorme, headers=auth_admin)
        assert r.status_code == 413
