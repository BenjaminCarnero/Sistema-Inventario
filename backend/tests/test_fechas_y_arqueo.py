"""Zona horaria en los filtros, arqueo por turno y restauración de respaldos.

Todo esto salió de una revisión completa: son los bordes donde el sistema
contaba mal sin que nadie se diera cuenta.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import auth, models, respaldos
from app.fechas import filtro_de_dias, rango_local_en_utc
from tests.conftest import cabecera, crear_usuario, token_de


def _hoy_local() -> str:
    return datetime.now().date().isoformat()


class TestFiltrosPorFecha:
    """El día del comercio es el de su reloj de pared; la base guarda UTC.

    Comparar una fecha local contra una columna en UTC parece andar hasta que
    no: en Argentina, después de las 21:00 las dos dejan de coincidir.
    """

    def test_el_rango_del_dia_no_es_de_medianoche_a_medianoche_utc(self):
        hoy = datetime.now().date()
        inicio, fin = rango_local_en_utc(hoy, hoy)

        # Sea cual sea la zona, el rango dura exactamente un día
        assert fin - inicio == timedelta(days=1)
        # Y arranca en la medianoche LOCAL, convertida a UTC
        esperado = datetime.combine(hoy, datetime.min.time()).astimezone(timezone.utc)
        assert inicio == esperado.replace(tzinfo=None)

    def test_sin_parametros_no_filtra_nada(self):
        assert filtro_de_dias(None, None) == (None, None)

    def test_una_fecha_mal_escrita_se_rechaza(self):
        with pytest.raises(Exception):
            filtro_de_dias("12-08-2026", None)

    def test_el_historial_de_stock_encuentra_lo_de_hoy(self, client, auth_admin, producto):
        """Con el filtro naive, un movimiento hecho a la tarde en Argentina
        podía quedar fuera del rango de su propio día."""
        client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "tipo_movimiento": "INGRESO", "cantidad": 5,
        })

        r = client.get(f"/stock/movimientos?desde={_hoy_local()}&hasta={_hoy_local()}",
                       headers=auth_admin)
        assert r.status_code == 200
        assert len(r.json()) == 1, "el movimiento de hoy tiene que caer dentro de hoy"

    def test_la_auditoria_encuentra_lo_de_hoy(self, client, auth_admin, admin, db):
        crear_usuario(db, "otro", "1234", models.RolEnum.CAJERO.value)
        usuario = db.query(models.Usuario).filter(models.Usuario.nombre == "otro").first()
        client.put(f"/auth/users/{usuario.id}", headers=auth_admin, json={
            "nombre": "otro", "rol_id": 2, "estado": True,
        })

        r = client.get(f"/auditoria/?desde={_hoy_local()}&hasta={_hoy_local()}", headers=auth_admin)
        assert r.status_code == 200
        assert len(r.json()) >= 1


class TestArqueoConDosCajas:
    def _encargado(self, client, db):
        crear_usuario(db, "encargado", "123456", models.RolEnum.ENCARGADO.value)
        return cabecera(token_de(client, "encargado", "123456"))

    def test_la_devolucion_le_descuenta_a_una_sola_caja(
        self, client, auth_admin, admin, producto, sin_iva, db
    ):
        """Antes se restaba por ventana de tiempo: con dos cajas abiertas, la
        misma devolución les daba faltante a las dos."""
        auth_encargado = self._encargado(client, db)

        # Dos cajas abiertas al mismo tiempo, cada una con su cajero
        client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 1000})
        caja_b = client.post("/cajas/abrir", headers=auth_encargado, json={"monto_inicial": 1000}).json()

        # El admin vende y después devuelve: la plata sale de SU cajón
        venta = client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [], "metodo_devolucion": "EFECTIVO",
        })
        assert r.status_code == 201, r.text

        # La caja del encargado no vendió ni devolvió nada: cierra sin diferencia
        cierre = client.put(f"/cajas/{caja_b['id']}/cerrar", headers=auth_encargado, json={
            "monto_final_declarado": 1000,
        })
        assert cierre.status_code == 200, cierre.text
        assert cierre.json()["diferencia_calculada"] == 0, (
            "la devolución de la otra caja no puede darle faltante a esta"
        )

    def test_la_caja_que_devolvio_si_lo_descuenta(
        self, client, auth_admin, admin, producto, sin_iva, db
    ):
        caja = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 1000}).json()

        venta = client.post("/ventas/", headers=auth_admin, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [], "metodo_devolucion": "EFECTIVO",
        })

        # Vendió 1000 y devolvió 1000: en el cajón quedan los 1000 iniciales
        cierre = client.put(f"/cajas/{caja['id']}/cerrar", headers=auth_admin, json={
            "monto_final_declarado": 1000,
        })
        assert cierre.json()["diferencia_calculada"] == 0


class TestPoliticaDePin:
    def test_el_instalador_usa_el_mismo_minimo_que_la_api(self):
        """seed_admin.py tenía 4 fijo, así que el primer administrador era el
        único que podía saltarse el mínimo de 8 de su propio rol."""
        import seed_admin

        assert seed_admin.PIN_MINIMO == auth.pin_minimo(models.RolEnum.ADMIN.value)
        assert seed_admin.PIN_MINIMO == 8


class TestStockConcurrente:
    def test_dos_ingresos_del_mismo_producto_se_suman_los_dos(
        self, client, auth_admin, producto, db
    ):
        """El `with_for_update()` no hace nada en SQLite: leyendo y sumando en
        Python, dos ingresos simultáneos se pisaban."""
        for _ in range(2):
            r = client.post("/stock/movimientos", headers=auth_admin, json={
                "producto_id": producto.id, "tipo_movimiento": "INGRESO", "cantidad": 10,
            })
            assert r.status_code == 201, r.text

        db.refresh(producto)
        assert producto.stock_actual == 120  # 100 + 10 + 10


class TestRestauracion:
    def test_se_puede_restaurar_lo_que_se_respaldo(self, client, auth_admin, producto, tmp_path, monkeypatch):
        """Un respaldo que nadie probó restaurar no es un respaldo."""
        import sqlite3
        import restaurar_respaldo

        monkeypatch.setattr(respaldos, "CARPETA", tmp_path)
        copia = respaldos.crear("prueba")
        assert copia is not None

        # La copia pasa la verificación que hace el restaurador
        restaurar_respaldo._verificar(copia)

        conexion = sqlite3.connect(str(copia))
        try:
            nombres = [f[0] for f in conexion.execute("select nombre from productos")]
            assert producto.nombre in nombres
        finally:
            conexion.close()

    def test_una_copia_dañada_no_pisa_la_base(self, tmp_path, monkeypatch):
        import restaurar_respaldo

        rota = tmp_path / "applify_20260101_000000_rota.db"
        rota.write_bytes(b"esto no es una base de datos")

        with pytest.raises(SystemExit):
            restaurar_respaldo._verificar(rota)

    def test_una_base_ajena_no_se_acepta(self, tmp_path):
        """Una SQLite válida pero de otro sistema no tiene por qué entrar."""
        import sqlite3
        import restaurar_respaldo

        ajena = tmp_path / "applify_20260101_000000_ajena.db"
        conexion = sqlite3.connect(str(ajena))
        conexion.execute("create table cualquiera (id integer)")
        conexion.commit()
        conexion.close()

        with pytest.raises(SystemExit):
            restaurar_respaldo._verificar(ajena)
