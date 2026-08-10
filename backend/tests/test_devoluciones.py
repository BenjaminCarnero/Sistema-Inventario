"""Devoluciones y anulaciones: stock, importes y estado de la venta."""
from app import models


def vender(client, auth, producto_id, cantidad=1, precio=1000.0, **extra):
    return client.post("/ventas/", json={
        "metodo_pago": "EFECTIVO",
        "detalles": [{"producto_id": producto_id, "cantidad": cantidad, "precio_unitario": precio}],
        **extra,
    }, headers=auth)


class TestDevolucionParcial:
    def test_repone_el_stock_devuelto(self, client, auth_admin, producto, db, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=5).json()
        db.refresh(producto)
        assert producto.stock_actual == 95

        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 2}],
        })
        assert r.status_code == 201
        db.refresh(producto)
        assert producto.stock_actual == 97

    def test_devuelve_el_importe_proporcional(self, client, auth_admin, producto, db, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=5).json()
        assert venta["total"] == 5000.0

        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 2}],
        })
        assert r.json()["total_devuelto"] == 2000.0

    def test_la_venta_queda_marcada_como_parcial(self, client, auth_admin, producto, db, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=5).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 1}],
        })
        guardada = db.query(models.Venta).filter(models.Venta.id == venta["id"]).one()
        assert guardada.estado == models.EstadoVentaEnum.CON_DEVOLUCION.value

    def test_registra_el_ingreso_de_stock(self, client, auth_admin, producto, db, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=3).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 1}],
        })
        ingresos = db.query(models.MovimientoStock).filter(
            models.MovimientoStock.tipo_movimiento == models.TipoMovimientoEnum.INGRESO.value
        ).all()
        assert len(ingresos) == 1
        assert ingresos[0].cantidad == 1


class TestAnulacion:
    def test_sin_detalles_devuelve_todo(self, client, auth_admin, producto, db, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=4).json()

        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "motivo": "Error de carga",
        })
        assert r.status_code == 201
        assert r.json()["es_anulacion"] is True
        assert r.json()["total_devuelto"] == 4000.0

        db.refresh(producto)
        assert producto.stock_actual == 100  # todo de vuelta

    def test_la_venta_queda_anulada(self, client, auth_admin, producto, db, sin_iva):
        venta = vender(client, auth_admin, producto.id).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={})
        guardada = db.query(models.Venta).filter(models.Venta.id == venta["id"]).one()
        assert guardada.estado == models.EstadoVentaEnum.ANULADA.value

    def test_no_se_puede_anular_dos_veces(self, client, auth_admin, producto, sin_iva):
        venta = vender(client, auth_admin, producto.id).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={})
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={})
        assert r.status_code == 400

    def test_la_venta_no_se_borra(self, client, auth_admin, producto, db, sin_iva):
        """Anular deja rastro: el historial tiene que ser auditable."""
        venta = vender(client, auth_admin, producto.id).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={})
        assert db.query(models.Venta).filter(models.Venta.id == venta["id"]).count() == 1


class TestLimites:
    def test_no_se_puede_devolver_mas_de_lo_vendido(self, client, auth_admin, producto, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=2).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 5}],
        })
        assert r.status_code == 400

    def test_dos_devoluciones_no_superan_lo_vendido(self, client, auth_admin, producto, db, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=3).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 2}],
        })
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 2}],
        })
        assert r.status_code == 400
        db.refresh(producto)
        assert producto.stock_actual == 99  # sólo volvieron las 2 primeras

    def test_no_se_puede_devolver_un_producto_ajeno_a_la_venta(self, client, auth_admin, producto, db, sin_iva):
        otro = models.Producto(
            codigo_barras="999", nombre="Otro", precio_venta=50, costo=10, stock_actual=5,
        )
        db.add(otro)
        db.commit()
        db.refresh(otro)

        venta = vender(client, auth_admin, producto.id).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": otro.id, "cantidad": 1}],
        })
        assert r.status_code == 400

    def test_el_disponible_refleja_lo_ya_devuelto(self, client, auth_admin, producto, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=5).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 2}],
        })
        disponible = client.get(f"/devoluciones/venta/{venta['id']}/disponible", headers=auth_admin).json()
        assert disponible[0]["cantidad_vendida"] == 5
        assert disponible[0]["cantidad_devuelta"] == 2
        assert disponible[0]["cantidad_disponible"] == 3


class TestPermisos:
    def test_un_cajero_no_puede_devolver(self, client, auth_admin, auth_cajero, producto, sin_iva):
        """Devolver plata mueve la caja: hace falta admin o encargado."""
        venta = vender(client, auth_admin, producto.id).json()
        r = client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_cajero, json={})
        assert r.status_code == 403


class TestImpactoEnReportes:
    def test_la_recaudacion_del_dia_descuenta_lo_devuelto(self, client, auth_admin, producto, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=3).json()
        assert client.get("/reportes/kpi", headers=auth_admin).json()["ventas_hoy_local"] == 3000.0

        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 1}],
        })
        assert client.get("/reportes/kpi", headers=auth_admin).json()["ventas_hoy_local"] == 2000.0

    def test_el_producto_devuelto_no_cuenta_como_vendido(self, client, auth_admin, producto, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=5).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 2}],
        })
        top = client.get("/reportes/top_productos", headers=auth_admin).json()
        assert top[0]["cantidad_vendida"] == 3

    def test_la_rentabilidad_descuenta_lo_devuelto(self, client, auth_admin, producto, sin_iva):
        venta = vender(client, auth_admin, producto.id, cantidad=5).json()
        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad": 5}],
        })
        rentabilidad = client.get("/reportes/rentabilidad", headers=auth_admin).json()
        # Se devolvió todo: no quedó ni ingreso ni ganancia
        assert all(r["ganancia"] == 0 for r in rentabilidad)
