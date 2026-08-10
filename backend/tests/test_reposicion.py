"""Proveedores y pedidos de reposición.

El circuito completo: se detecta el faltante, se arma el pedido, queda en
camino, llega y carga el stock.
"""
import pytest

from app import models


@pytest.fixture
def proveedor(client, auth_admin):
    return client.post("/proveedores/", headers=auth_admin, json={
        "nombre": "Distribuidora Sur", "telefono": "11-5555-1234",
    }).json()


@pytest.fixture
def faltante(db):
    """Producto con dos unidades: por debajo del umbral de cinco."""
    p = models.Producto(
        codigo_barras="7790000000999",
        nombre="CocaCola 500",
        precio_venta=1500.0,
        costo=900.0,
        stock_actual=2,
        cantidad_pedido_habitual=24,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


class TestProveedores:
    def test_alta_y_listado(self, client, auth_admin):
        r = client.post("/proveedores/", headers=auth_admin, json={"nombre": "Mayorista Centro"})
        assert r.status_code == 201
        nombres = [p["nombre"] for p in client.get("/proveedores/", headers=auth_admin).json()]
        assert "Mayorista Centro" in nombres

    def test_no_permite_nombres_repetidos(self, client, auth_admin, proveedor):
        r = client.post("/proveedores/", headers=auth_admin, json={"nombre": "Distribuidora Sur"})
        assert r.status_code == 400

    def test_el_telefono_queda_listo_para_whatsapp(self, client, auth_admin, proveedor):
        """Los guiones romperían el enlace wa.me, así que se limpian al guardar."""
        assert proveedor["telefono"] == "1155551234"

    def test_rechaza_un_telefono_que_no_lo_es(self, client, auth_admin):
        r = client.post("/proveedores/", headers=auth_admin, json={
            "nombre": "Corto", "telefono": "123",
        })
        assert r.status_code == 400

    def test_el_cajero_no_los_ve(self, client, auth_cajero, admin):
        assert client.get("/proveedores/", headers=auth_cajero).status_code == 403

    def test_borrarlo_deja_los_productos_sin_proveedor(self, client, auth_admin, proveedor, faltante, db):
        client.put(f"/productos/{faltante.id}", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
        })
        assert client.delete(f"/proveedores/{proveedor['id']}", headers=auth_admin).status_code == 204
        db.refresh(faltante)
        assert faltante.proveedor_id is None

    def test_con_pedidos_se_desactiva_en_vez_de_borrarse(self, client, auth_admin, proveedor, faltante, db):
        """Los pedidos viejos tienen que seguir diciendo a quién se le compró."""
        client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 10}],
        })
        client.delete(f"/proveedores/{proveedor['id']}", headers=auth_admin)

        guardado = db.query(models.Proveedor).filter(models.Proveedor.id == proveedor["id"]).first()
        assert guardado is not None and guardado.activo is False
        # Y deja de aparecer en la lista de todos los días
        assert client.get("/proveedores/", headers=auth_admin).json() == []

    def test_no_se_asigna_un_proveedor_que_no_existe(self, client, auth_admin, faltante):
        r = client.put(f"/productos/{faltante.id}", headers=auth_admin, json={"proveedor_id": 9999})
        assert r.status_code == 400


class TestSugerencia:
    def test_trae_lo_que_esta_por_debajo_del_umbral(self, client, auth_admin, faltante, producto):
        grupos = client.get("/pedidos/reponer", headers=auth_admin).json()
        nombres = [i["producto_nombre"] for g in grupos for i in g["items"]]
        assert "CocaCola 500" in nombres        # tiene 2
        assert "Producto de prueba" not in nombres  # tiene 100

    def test_propone_la_cantidad_habitual(self, client, auth_admin, faltante):
        item = client.get("/pedidos/reponer", headers=auth_admin).json()[0]["items"][0]
        assert item["cantidad_sugerida"] == 24

    def test_sin_cantidad_habitual_no_inventa_un_numero(self, client, auth_admin, db):
        db.add(models.Producto(
            codigo_barras="111", nombre="Sin costumbre", precio_venta=10, costo=5, stock_actual=1,
        ))
        db.commit()
        item = client.get("/pedidos/reponer", headers=auth_admin).json()[0]["items"][0]
        assert item["cantidad_sugerida"] is None

    def test_agrupa_por_proveedor(self, client, auth_admin, proveedor, faltante, db):
        client.put(f"/productos/{faltante.id}", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
        })
        db.add(models.Producto(
            codigo_barras="222", nombre="Huérfano", precio_venta=10, costo=5, stock_actual=0,
        ))
        db.commit()

        grupos = client.get("/pedidos/reponer", headers=auth_admin).json()
        por_nombre = {g["proveedor_nombre"]: g for g in grupos}
        assert por_nombre["Distribuidora Sur"]["items"][0]["producto_nombre"] == "CocaCola 500"
        # Los que no tienen proveedor no se esconden: van en su propio grupo
        assert por_nombre[None]["items"][0]["producto_nombre"] == "Huérfano"

    def test_avisa_lo_que_ya_esta_en_camino(self, client, auth_admin, proveedor, faltante):
        """Es el dato que evita pedir dos veces lo mismo."""
        client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 24}],
        })
        item = client.get("/pedidos/reponer", headers=auth_admin).json()[0]["items"][0]
        assert item["ya_pedido"] == 24

    def test_lo_recibido_deja_de_contar_como_en_camino(self, client, auth_admin, proveedor, faltante):
        pedido = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 24}],
        }).json()
        client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={"detalles": []})

        grupos = client.get("/pedidos/reponer", headers=auth_admin).json()
        assert grupos == []  # con 26 unidades ya no falta


class TestAltaDePedido:
    def test_no_toca_el_stock(self, client, auth_admin, proveedor, faltante, db):
        """Todavía no llegó: sumarlo acá sería vender lo que no está."""
        client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 24}],
        })
        db.refresh(faltante)
        assert faltante.stock_actual == 2

    def test_queda_pendiente(self, client, auth_admin, proveedor, faltante):
        pedido = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 24}],
        }).json()
        assert pedido["estado"] == "PENDIENTE"
        assert pedido["proveedor_nombre"] == "Distribuidora Sur"

    def test_suma_el_producto_repetido(self, client, auth_admin, proveedor, faltante):
        pedido = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [
                {"producto_id": faltante.id, "cantidad": 10},
                {"producto_id": faltante.id, "cantidad": 14},
            ],
        }).json()
        assert len(pedido["detalles"]) == 1
        assert pedido["detalles"][0]["cantidad"] == 24

    def test_rechaza_un_pedido_vacio(self, client, auth_admin, proveedor):
        r = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"], "detalles": [],
        })
        assert r.status_code == 400

    def test_rechaza_un_proveedor_inexistente(self, client, auth_admin, faltante):
        r = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": 9999,
            "detalles": [{"producto_id": faltante.id, "cantidad": 1}],
        })
        assert r.status_code == 404

    def test_rechaza_un_producto_inexistente(self, client, auth_admin, proveedor):
        r = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": 9999, "cantidad": 1}],
        })
        assert r.status_code == 404

    def test_el_cajero_no_puede_pedir(self, client, auth_cajero, admin, proveedor, faltante):
        r = client.post("/pedidos/", headers=auth_cajero, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 1}],
        })
        assert r.status_code == 403


class TestRecepcion:
    def _pedir(self, client, auth, proveedor, producto, cantidad=24):
        return client.post("/pedidos/", headers=auth, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": producto.id, "cantidad": cantidad}],
        }).json()

    def test_carga_el_stock_de_una(self, client, auth_admin, proveedor, faltante, db):
        pedido = self._pedir(client, auth_admin, proveedor, faltante)
        r = client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={"detalles": []})
        assert r.status_code == 200
        db.refresh(faltante)
        assert faltante.stock_actual == 26  # 2 + 24

    def test_deja_el_movimiento_de_stock(self, client, auth_admin, proveedor, faltante, db):
        pedido = self._pedir(client, auth_admin, proveedor, faltante)
        client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={"detalles": []})

        movimiento = db.query(models.MovimientoStock).one()
        assert movimiento.tipo_movimiento == "INGRESO"
        assert movimiento.cantidad == 24
        assert f"Pedido #{pedido['id']}" in movimiento.motivo
        assert "Distribuidora Sur" in movimiento.motivo

    def test_se_puede_recibir_menos_de_lo_pedido(self, client, auth_admin, proveedor, faltante, db):
        """El proveedor manda lo que tiene: casi nunca coincide con lo pedido."""
        pedido = self._pedir(client, auth_admin, proveedor, faltante)
        client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={
            "detalles": [{"producto_id": faltante.id, "cantidad_recibida": 20}],
        })
        db.refresh(faltante)
        assert faltante.stock_actual == 22  # 2 + 20, no 26

    def test_recibir_cero_no_suma_nada(self, client, auth_admin, proveedor, faltante, db):
        pedido = self._pedir(client, auth_admin, proveedor, faltante)
        client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={
            "detalles": [{"producto_id": faltante.id, "cantidad_recibida": 0}],
        })
        db.refresh(faltante)
        assert faltante.stock_actual == 2
        assert db.query(models.MovimientoStock).count() == 0

    def test_guarda_cuanto_llego_de_verdad(self, client, auth_admin, proveedor, faltante):
        pedido = self._pedir(client, auth_admin, proveedor, faltante)
        recibido = client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={
            "detalles": [{"producto_id": faltante.id, "cantidad_recibida": 20}],
        }).json()
        assert recibido["detalles"][0]["cantidad"] == 24
        assert recibido["detalles"][0]["cantidad_recibida"] == 20
        assert recibido["fecha_recepcion"] is not None

    def test_no_se_recibe_dos_veces(self, client, auth_admin, proveedor, faltante, db):
        """Recibirlo de nuevo duplicaría el stock sin que nadie se entere."""
        pedido = self._pedir(client, auth_admin, proveedor, faltante)
        client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={"detalles": []})
        r = client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={"detalles": []})
        assert r.status_code == 400
        db.refresh(faltante)
        assert faltante.stock_actual == 26

    def test_rechaza_un_producto_ajeno_al_pedido(self, client, auth_admin, proveedor, faltante, producto):
        pedido = self._pedir(client, auth_admin, proveedor, faltante)
        r = client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={
            "detalles": [{"producto_id": producto.id, "cantidad_recibida": 5}],
        })
        assert r.status_code == 400


class TestCancelacion:
    def test_cancelar_no_toca_el_stock(self, client, auth_admin, proveedor, faltante, db):
        pedido = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 24}],
        }).json()
        r = client.post(f"/pedidos/{pedido['id']}/cancelar", headers=auth_admin)
        assert r.status_code == 200 and r.json()["estado"] == "CANCELADO"
        db.refresh(faltante)
        assert faltante.stock_actual == 2

    def test_lo_cancelado_ya_no_esta_en_camino(self, client, auth_admin, proveedor, faltante):
        pedido = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 24}],
        }).json()
        client.post(f"/pedidos/{pedido['id']}/cancelar", headers=auth_admin)

        item = client.get("/pedidos/reponer", headers=auth_admin).json()[0]["items"][0]
        assert item["ya_pedido"] == 0

    def test_no_se_cancela_lo_que_ya_llego(self, client, auth_admin, proveedor, faltante):
        pedido = client.post("/pedidos/", headers=auth_admin, json={
            "proveedor_id": proveedor["id"],
            "detalles": [{"producto_id": faltante.id, "cantidad": 24}],
        }).json()
        client.post(f"/pedidos/{pedido['id']}/recibir", headers=auth_admin, json={"detalles": []})
        r = client.post(f"/pedidos/{pedido['id']}/cancelar", headers=auth_admin)
        assert r.status_code == 400


class TestListado:
    def test_filtra_por_estado(self, client, auth_admin, proveedor, faltante):
        for _ in range(2):
            client.post("/pedidos/", headers=auth_admin, json={
                "proveedor_id": proveedor["id"],
                "detalles": [{"producto_id": faltante.id, "cantidad": 5}],
            })
        primero = client.get("/pedidos/", headers=auth_admin).json()[-1]
        client.post(f"/pedidos/{primero['id']}/cancelar", headers=auth_admin)

        pendientes = client.get("/pedidos/?estado=PENDIENTE", headers=auth_admin).json()
        assert len(pendientes) == 1

    def test_rechaza_un_estado_inventado(self, client, auth_admin):
        assert client.get("/pedidos/?estado=VOLANDO", headers=auth_admin).status_code == 400
