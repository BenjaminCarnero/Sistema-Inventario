"""Cálculo de una venta: precio, IVA, descuentos, stock e idempotencia.

Es la parte del sistema donde un error se traduce directamente en plata mal
cobrada, así que es la que más cubierta está.
"""
from app import models


def vender(client, auth, producto_id, cantidad=1, precio=1000.0, **extra):
    cuerpo = {
        "metodo_pago": "EFECTIVO",
        "detalles": [{"producto_id": producto_id, "cantidad": cantidad, "precio_unitario": precio}],
        **extra,
    }
    return client.post("/ventas/", json=cuerpo, headers=auth)


class TestPrecio:
    def test_usa_el_precio_del_catalogo_y_no_el_del_cliente(self, client, auth_admin, producto, sin_iva):
        """El agujero más grave que tuvo el sistema: el cliente fijaba el precio."""
        r = vender(client, auth_admin, producto.id, cantidad=1, precio=1.0)
        assert r.status_code == 201
        # Se envió $1 pero el producto vale $1000
        assert r.json()["total"] == 1000.0

    def test_el_subtotal_guardado_tambien_usa_el_precio_real(self, client, auth_admin, producto, sin_iva):
        r = vender(client, auth_admin, producto.id, cantidad=3, precio=1.0)
        detalle = r.json()["detalles"][0]
        assert detalle["precio_unitario"] == 1000.0
        assert detalle["subtotal"] == 3000.0


class TestValidaciones:
    def test_rechaza_cantidad_negativa(self, client, auth_admin, producto):
        r = vender(client, auth_admin, producto.id, cantidad=-5)
        assert r.status_code == 422

    def test_rechaza_cantidad_cero(self, client, auth_admin, producto):
        r = vender(client, auth_admin, producto.id, cantidad=0)
        assert r.status_code == 422

    def test_rechaza_venta_sin_productos(self, client, auth_admin):
        r = client.post("/ventas/", json={"metodo_pago": "EFECTIVO", "detalles": []}, headers=auth_admin)
        assert r.status_code == 400

    def test_rechaza_metodo_de_pago_inventado(self, client, auth_admin, producto):
        r = vender(client, auth_admin, producto.id, metodo_pago="REGALO")
        assert r.status_code == 400

    def test_rechaza_producto_inexistente(self, client, auth_admin, sin_iva):
        r = vender(client, auth_admin, 999999)
        assert r.status_code == 404

    def test_rechaza_monto_recibido_negativo(self, client, auth_admin, producto):
        r = vender(client, auth_admin, producto.id, monto_recibido=-100)
        assert r.status_code == 400


class TestStock:
    def test_la_venta_descuenta_stock(self, client, auth_admin, producto, db, sin_iva):
        vender(client, auth_admin, producto.id, cantidad=7)
        db.refresh(producto)
        assert producto.stock_actual == 93

    def test_registra_el_movimiento_de_egreso(self, client, auth_admin, producto, db, sin_iva):
        vender(client, auth_admin, producto.id, cantidad=2)
        movimiento = db.query(models.MovimientoStock).one()
        assert movimiento.tipo_movimiento == models.TipoMovimientoEnum.EGRESO.value
        assert movimiento.cantidad == 2

    def test_puede_exigir_stock_suficiente(self, client, auth_admin, producto, db, sin_iva):
        db.add(models.Configuracion(
            clave="permitir_stock_negativo", valor="false", tipo="boolean", categoria="pos",
        ))
        db.commit()
        r = vender(client, auth_admin, producto.id, cantidad=500)
        assert r.status_code == 400
        db.refresh(producto)
        assert producto.stock_actual == 100  # la transacción no dejó rastro


class TestIva:
    def _configurar(self, db, porcentaje, incluido):
        db.add(models.Configuracion(
            clave="iva_porcentaje", valor=str(porcentaje), tipo="number", categoria="impuestos",
        ))
        db.add(models.Configuracion(
            clave="iva_incluido_en_precio",
            valor="true" if incluido else "false", tipo="boolean", categoria="impuestos",
        ))
        db.commit()

    def test_incluido_en_el_precio_no_cambia_el_total(self, client, auth_admin, producto, db):
        """Modo Argentina: el precio de góndola ya trae el IVA adentro."""
        self._configurar(db, 21, incluido=True)
        r = vender(client, auth_admin, producto.id)
        datos = r.json()
        assert datos["total"] == 1000.0
        # 1000 - 1000/1.21 = 173.55
        assert datos["iva_monto"] == 173.55
        assert datos["iva_porcentaje"] == 21

    def test_agregado_al_cobrar_suma_al_total(self, client, auth_admin, producto, db):
        """Modo EE.UU.: el impuesto se suma sobre el precio."""
        self._configurar(db, 21, incluido=False)
        datos = vender(client, auth_admin, producto.id).json()
        assert datos["total"] == 1210.0
        assert datos["iva_monto"] == 210.0

    def test_queda_guardada_la_alicuota_usada(self, client, auth_admin, producto, db):
        """Si mañana cambia el IVA, los tickets viejos no se alteran."""
        self._configurar(db, 10.5, incluido=False)
        datos = vender(client, auth_admin, producto.id).json()
        assert datos["iva_porcentaje"] == 10.5
        assert datos["total"] == 1105.0


class TestDescuentos:
    def _descuento(self, db, tipo, valor, producto_id=None):
        d = models.Descuento(
            nombre="Promo", tipo=tipo, valor=valor, producto_id=producto_id, activo=True,
        )
        db.add(d)
        db.commit()
        db.refresh(d)
        return d

    def test_porcentaje_sobre_toda_la_venta(self, client, auth_admin, producto, db, sin_iva):
        d = self._descuento(db, "PORCENTAJE", 15)
        datos = vender(client, auth_admin, producto.id, cantidad=2, descuento_id=d.id).json()
        assert datos["total"] == 1700.0  # 2000 - 15%

    def test_monto_fijo(self, client, auth_admin, producto, db, sin_iva):
        d = self._descuento(db, "MONTO", 500)
        datos = vender(client, auth_admin, producto.id, cantidad=2, descuento_id=d.id).json()
        assert datos["total"] == 1500.0

    def test_el_monto_fijo_no_deja_el_total_negativo(self, client, auth_admin, producto, db, sin_iva):
        d = self._descuento(db, "MONTO", 99999)
        datos = vender(client, auth_admin, producto.id, descuento_id=d.id).json()
        assert datos["total"] == 0.0

    def test_rechaza_descuento_inactivo(self, client, auth_admin, producto, db, sin_iva):
        d = self._descuento(db, "PORCENTAJE", 10)
        d.activo = False
        db.commit()
        r = vender(client, auth_admin, producto.id, descuento_id=d.id)
        assert r.status_code == 400


class TestIdempotencia:
    def test_el_mismo_uuid_no_cobra_dos_veces(self, client, auth_admin, producto, db, sin_iva):
        """Un reintento de la sincronización offline no debe duplicar la venta."""
        cuerpo = {
            "uuid_cliente": "abc-123",
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }
        primera = client.post("/ventas/", json=cuerpo, headers=auth_admin).json()
        segunda = client.post("/ventas/", json=cuerpo, headers=auth_admin).json()
        tercera = client.post("/ventas/", json=cuerpo, headers=auth_admin).json()

        assert primera["id"] == segunda["id"] == tercera["id"]
        assert db.query(models.Venta).count() == 1
        db.refresh(producto)
        assert producto.stock_actual == 99  # descontó una sola vez


class TestAislamiento:
    def test_el_cajero_solo_ve_sus_ventas(self, client, auth_admin, auth_cajero, producto, sin_iva):
        vender(client, auth_admin, producto.id)
        vender(client, auth_cajero, producto.id)

        del_cajero = client.get("/ventas/", headers=auth_cajero).json()
        del_admin = client.get("/ventas/", headers=auth_admin).json()

        assert len(del_cajero) == 1
        assert len(del_admin) == 2
