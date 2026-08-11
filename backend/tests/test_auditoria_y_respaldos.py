"""Respaldos, auditoría, freno al login y tope de devoluciones."""
from datetime import date, datetime, timedelta, timezone

from app import models, respaldos
from app.routers.reportes import rango_local_en_utc, fecha_local_de
from tests.conftest import crear_usuario, token_de, cabecera


class TestRespaldos:
    def test_la_copia_se_puede_abrir_y_tiene_los_datos(self, client, auth_admin, producto, tmp_path, monkeypatch):
        """Una copia que no se puede abrir es peor que no tener copia."""
        import sqlite3
        monkeypatch.setattr(respaldos, "CARPETA", tmp_path)

        ruta = respaldos.crear("prueba")
        assert ruta is not None and ruta.exists()

        copia = sqlite3.connect(str(ruta))
        try:
            assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            nombres = [f[0] for f in copia.execute("select nombre from productos")]
            assert producto.nombre in nombres
        finally:
            copia.close()

    def test_conserva_solo_las_ultimas(self, client, auth_admin, tmp_path, monkeypatch):
        monkeypatch.setattr(respaldos, "CARPETA", tmp_path)
        monkeypatch.setattr(respaldos, "MAXIMO_A_CONSERVAR", 3)

        for _ in range(5):
            respaldos.crear("prueba")

        assert len(respaldos.listar()) == 3

    def test_el_cajero_no_puede_descargar_la_base(self, client, auth_cajero, admin):
        """La copia trae las ventas y los PIN hasheados de todos."""
        assert client.get("/respaldos/", headers=auth_cajero).status_code == 403
        assert client.post("/respaldos/", headers=auth_cajero).status_code == 403

    def test_no_se_puede_pedir_un_archivo_de_afuera(self, client, auth_admin):
        """Sin este chequeo el nombre serviría para bajarse el .env."""
        for nombre in ("../.env", "applify_../../.env.db", "otra_cosa.db"):
            r = client.get(f"/respaldos/{nombre}", headers=auth_admin)
            assert r.status_code in (404, 400), nombre


class TestAuditoria:
    def test_registra_el_cambio_de_precio(self, client, auth_admin, producto):
        client.put(f"/productos/{producto.id}", headers=auth_admin, json={"precio_venta": 1500})

        entradas = client.get("/auditoria/?entidad=producto", headers=auth_admin).json()
        cambio = [e for e in entradas if e["campo"] == "precio_venta"][0]
        assert cambio["valor_anterior"] == "1000.0"
        assert cambio["valor_nuevo"] == "1500.0"
        assert cambio["usuario_nombre"] == "admin"

    def test_no_ensucia_el_registro_con_cambios_que_no_cambian_nada(self, client, auth_admin, producto):
        client.put(f"/productos/{producto.id}", headers=auth_admin, json={"precio_venta": 1000})
        entradas = client.get("/auditoria/?entidad=producto", headers=auth_admin).json()
        assert [e for e in entradas if e["campo"] == "precio_venta"] == []

    def test_ignora_los_campos_que_no_mueven_plata(self, client, auth_admin, producto):
        client.put(f"/productos/{producto.id}", headers=auth_admin, json={"nombre": "Otro nombre"})
        entradas = client.get("/auditoria/?entidad=producto", headers=auth_admin).json()
        assert [e for e in entradas if e["campo"] == "nombre"] == []

    def test_registra_el_cambio_de_configuracion(self, client, auth_admin):
        client.put("/configuracion/", headers=auth_admin, json={"valores": {"iva_porcentaje": 10.5}})
        entradas = client.get("/auditoria/?entidad=configuracion", headers=auth_admin).json()
        assert entradas[0]["campo"] == "iva_porcentaje"
        assert entradas[0]["valor_nuevo"] == "10.5"

    def test_registra_el_cambio_de_rol(self, client, auth_admin, db):
        otro = crear_usuario(db, "pepe", "123456", models.RolEnum.CAJERO.value)
        client.put(f"/auth/users/{otro.id}", headers=auth_admin, json={
            "nombre": "pepe", "rol_id": models.RolEnum.ENCARGADO.value, "estado": True,
        })
        entradas = client.get("/auditoria/?entidad=usuario", headers=auth_admin).json()
        assert entradas[0]["campo"] == "rol_id"
        assert entradas[0]["valor_anterior"] == "3" and entradas[0]["valor_nuevo"] == "2"

    def test_el_encargado_no_puede_leer_la_auditoria(self, client, db, admin):
        crear_usuario(db, "encargado", "123456", models.RolEnum.ENCARGADO.value)
        auth = cabecera(token_de(client, "encargado", "123456"))
        assert client.get("/auditoria/", headers=auth).status_code == 403

    def test_el_logo_no_entra_entero_en_el_registro(self, client, auth_admin):
        """Una imagen embebida volvería la auditoría ilegible."""
        logo = "data:image/png;base64," + "A" * 5000
        client.put("/configuracion/", headers=auth_admin, json={"valores": {"marca_logo_url": logo}})
        entradas = client.get("/auditoria/?entidad=configuracion", headers=auth_admin).json()
        assert len(entradas[0]["valor_nuevo"]) < 200


class TestFrenoAlLogin:
    def test_los_intentos_sobreviven_al_reinicio(self, client, admin, db):
        """Antes vivían en memoria: reiniciar el servidor limpiaba el contador."""
        for _ in range(5):
            client.post("/auth/login", data={"username": "admin", "password": "mal"})

        assert db.query(models.IntentoLogin).count() == 5
        assert client.post("/auth/login", data={"username": "admin", "password": "mal"}).status_code == 429

    def test_entrar_bien_borra_los_fallos(self, client, admin, db):
        for _ in range(3):
            client.post("/auth/login", data={"username": "admin", "password": "mal"})
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})
        assert db.query(models.IntentoLogin).count() == 0


class TestPinPorRol:
    def test_el_admin_necesita_un_pin_largo(self, client, auth_admin):
        r = client.post("/auth/register", headers=auth_admin, json={
            "nombre": "admin2", "pin_acceso": "1234", "rol_id": 1, "estado": True,
        })
        assert r.status_code == 400

    def test_al_cajero_le_alcanza_con_cuatro(self, client, auth_admin):
        r = client.post("/auth/register", headers=auth_admin, json={
            "nombre": "cajero2", "pin_acceso": "1234", "rol_id": 3, "estado": True,
        })
        assert r.status_code == 201

    def test_el_admin_con_pin_largo_entra(self, client, auth_admin):
        r = client.post("/auth/register", headers=auth_admin, json={
            "nombre": "admin3", "pin_acceso": "unaClaveLarga", "rol_id": 1, "estado": True,
        })
        assert r.status_code == 201


class TestTopeDeDevoluciones:
    def _encargado(self, client, db):
        crear_usuario(db, "encargado", "123456", models.RolEnum.ENCARGADO.value)
        return cabecera(token_de(client, "encargado", "123456"))

    def _vender(self, client, auth, producto, cantidad):
        return client.post("/ventas/", headers=auth, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": cantidad, "precio_unitario": 1000}],
        })

    def test_sin_tope_configurado_no_molesta(self, client, auth_admin, producto, sin_iva, db):
        auth = self._encargado(client, db)
        venta = self._vender(client, auth_admin, producto, 5).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 5}],
        })
        assert r.status_code == 201

    def test_el_encargado_no_pasa_el_tope(self, client, auth_admin, producto, sin_iva, db):
        client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"devolucion_tope_encargado": 2000},
        })
        auth = self._encargado(client, db)
        venta = self._vender(client, auth_admin, producto, 5).json()

        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 3}],  # 3000
        })
        assert r.status_code == 403

    def test_rechazar_no_deja_el_stock_tocado(self, client, auth_admin, producto, sin_iva, db):
        """Se verifica antes de mover nada, sin depender del rollback."""
        client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"devolucion_tope_encargado": 2000},
        })
        auth = self._encargado(client, db)
        venta = self._vender(client, auth_admin, producto, 5).json()
        db.refresh(producto)
        stock_antes = producto.stock_actual

        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 3}],
        })
        db.refresh(producto)
        assert producto.stock_actual == stock_antes
        assert db.query(models.Devolucion).count() == 0

    def test_debajo_del_tope_pasa(self, client, auth_admin, producto, sin_iva, db):
        client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"devolucion_tope_encargado": 2000},
        })
        auth = self._encargado(client, db)
        venta = self._vender(client, auth_admin, producto, 5).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 1}],  # 1000
        })
        assert r.status_code == 201

    def test_el_admin_no_tiene_tope(self, client, auth_admin, producto, sin_iva):
        client.put("/configuracion/", headers=auth_admin, json={
            "valores": {"devolucion_tope_encargado": 2000},
        })
        venta = self._vender(client, auth_admin, producto, 5).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 5}],  # 5000
        })
        assert r.status_code == 201


class TestDiaDelLocal:
    """El día que cuenta es el del reloj de pared, no el de UTC.

    Guardando en UTC y comparando contra la fecha local, después de las 21:00
    en Argentina la recaudación del día pasaba a mostrar cero.
    """

    def test_el_rango_cubre_el_dia_local_entero(self):
        hoy = date.today()
        inicio, fin = rango_local_en_utc(hoy, hoy)
        assert (fin - inicio) == timedelta(days=1)

    def test_una_venta_de_ahora_cae_dentro_del_dia_de_hoy(self):
        ahora_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        inicio, fin = rango_local_en_utc(date.today(), date.today())
        assert inicio <= ahora_utc < fin

    def test_la_fecha_local_de_un_instante_utc(self):
        ahora_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        assert fecha_local_de(ahora_utc) == date.today()

    def test_la_recaudacion_de_hoy_no_depende_de_la_hora(self, client, auth_admin, producto, sin_iva):
        client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 2, "precio_unitario": 1000}],
        })
        kpi = client.get("/reportes/kpi", headers=auth_admin).json()
        assert kpi["ventas_hoy_local"] == 2000.0
        assert kpi["cantidad_ventas_hoy"] == 1

    def test_la_venta_de_hoy_aparece_en_el_grafico_diario(self, client, auth_admin, producto, sin_iva):
        client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        serie = client.get("/reportes/ventas_por_dia?dias=7", headers=auth_admin).json()
        de_hoy = [d for d in serie if d["fecha"] == date.today().isoformat()][0]
        assert de_hoy["total"] == 1000.0 and de_hoy["cantidad"] == 1

    def test_el_export_del_dia_trae_la_venta(self, client, auth_admin, producto, sin_iva):
        client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        })
        hoy = date.today().isoformat()
        ventas = client.get(f"/reportes/ventas_periodo?desde={hoy}&hasta={hoy}", headers=auth_admin).json()
        assert len(ventas) == 1
