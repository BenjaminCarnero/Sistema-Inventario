"""Entrada de mercadería, ajustes de inventario y arqueo de caja."""
from app import models
from app.fechas import hoy_local


def vender(client, auth, producto_id, cantidad=1, metodo="EFECTIVO"):
    return client.post("/ventas/", json={
        "metodo_pago": metodo,
        "detalles": [{"producto_id": producto_id, "cantidad": cantidad, "precio_unitario": 1000}],
    }, headers=auth)


class TestEntradaDeMercaderia:
    def test_el_ingreso_suma_al_stock(self, client, auth_admin, producto, db):
        r = client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 50,
            "tipo_movimiento": "INGRESO", "motivo": "Compra a proveedor",
        })
        assert r.status_code == 201
        db.refresh(producto)
        assert producto.stock_actual == 150

    def test_deja_registro_de_quien_y_por_que(self, client, auth_admin, producto, db, admin):
        client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 10,
            "tipo_movimiento": "INGRESO", "motivo": "Reposición",
        })
        movimiento = db.query(models.MovimientoStock).one()
        assert movimiento.usuario_id == admin.id
        assert "Reposición" in movimiento.motivo

    def test_no_se_puede_dar_salida_a_mano(self, client, auth_admin, producto):
        """Las salidas las genera la venta: a mano se descuadraría el arqueo."""
        r = client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 5, "tipo_movimiento": "EGRESO",
        })
        assert r.status_code == 400

    def test_rechaza_producto_inexistente(self, client, auth_admin):
        r = client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": 999999, "cantidad": 5, "tipo_movimiento": "INGRESO",
        })
        assert r.status_code == 404


class TestAjustePorRecuento:
    def test_el_stock_queda_en_lo_contado(self, client, auth_admin, producto, db):
        r = client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 80,
            "tipo_movimiento": "AJUSTE", "motivo": "Recuento mensual",
        })
        assert r.status_code == 201
        db.refresh(producto)
        assert producto.stock_actual == 80  # el conteo manda, no la suma

    def test_registra_la_diferencia_encontrada(self, client, auth_admin, producto, db):
        client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 80, "tipo_movimiento": "AJUSTE",
        })
        movimiento = db.query(models.MovimientoStock).one()
        assert movimiento.cantidad == 20  # faltaban 20
        assert "100" in movimiento.motivo and "80" in movimiento.motivo

    def test_contar_cero_es_valido(self, client, auth_admin, producto, db):
        """Se agotó y el sistema no se enteró: hay que poder dejarlo en cero."""
        r = client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 0, "tipo_movimiento": "AJUSTE",
        })
        assert r.status_code == 201
        db.refresh(producto)
        assert producto.stock_actual == 0

    def test_un_ingreso_de_cero_no_tiene_sentido(self, client, auth_admin, producto):
        r = client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 0, "tipo_movimiento": "INGRESO",
        })
        assert r.status_code == 400

    def test_el_ajuste_tambien_puede_sumar(self, client, auth_admin, producto, db):
        client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 120, "tipo_movimiento": "AJUSTE",
        })
        db.refresh(producto)
        assert producto.stock_actual == 120


class TestHistorial:
    def test_muestra_entradas_y_salidas(self, client, auth_admin, producto, sin_iva):
        vender(client, auth_admin, producto.id, cantidad=2)
        client.post("/stock/movimientos", headers=auth_admin, json={
            "producto_id": producto.id, "cantidad": 10, "tipo_movimiento": "INGRESO",
        })
        historial = client.get(f"/stock/movimientos?producto_id={producto.id}", headers=auth_admin).json()
        tipos = {m["tipo_movimiento"] for m in historial}
        assert tipos == {"EGRESO", "INGRESO"}


class TestFiltrosDelHistorial:
    """El admin audita el inventario desde acá, así que tiene que poder acotar."""

    def _con_movimientos(self, client, auth, producto, sin_iva):
        vender(client, auth, producto.id, cantidad=2)
        client.post("/stock/movimientos", headers=auth, json={
            "producto_id": producto.id, "cantidad": 10, "tipo_movimiento": "INGRESO",
        })
        client.post("/stock/movimientos", headers=auth, json={
            "producto_id": producto.id, "cantidad": 90, "tipo_movimiento": "AJUSTE",
        })

    def test_filtra_por_tipo(self, client, auth_admin, producto, sin_iva):
        self._con_movimientos(client, auth_admin, producto, sin_iva)
        entradas = client.get("/stock/movimientos?tipo=INGRESO", headers=auth_admin).json()
        assert [m["tipo_movimiento"] for m in entradas] == ["INGRESO"]

    def test_rechaza_un_tipo_inventado(self, client, auth_admin):
        assert client.get("/stock/movimientos?tipo=ROBO", headers=auth_admin).status_code == 400

    def test_el_rango_incluye_el_dia_de_hoy_entero(self, client, auth_admin, producto, sin_iva):
        """Con `hasta` mal implementado, lo de hoy quedaba afuera del reporte.

        `hoy` tiene que salir de `hoy_local()`, la misma cuenta que hace el
        propio backend para decidir qué es "hoy" — no de
        `datetime.now(timezone.utc)`. Con ZONA_HORARIA sin configurar en el
        entorno de test, el filtro usa la hora del sistema, y la fecha en UTC
        y la fecha local difieren unas tres horas por día (más en otros husos):
        calcular "hoy" por otro lado hacía que el test fallara solo, sin que
        nadie tocara el código, en esa ventana horaria.
        """
        self._con_movimientos(client, auth_admin, producto, sin_iva)
        hoy = hoy_local().isoformat()
        movimientos = client.get(f"/stock/movimientos?desde={hoy}&hasta={hoy}", headers=auth_admin).json()
        assert len(movimientos) == 3

    def test_una_fecha_anterior_no_trae_nada(self, client, auth_admin, producto, sin_iva):
        self._con_movimientos(client, auth_admin, producto, sin_iva)
        assert client.get("/stock/movimientos?hasta=2020-01-01", headers=auth_admin).json() == []

    def test_rechaza_una_fecha_con_formato_raro(self, client, auth_admin):
        assert client.get("/stock/movimientos?desde=ayer", headers=auth_admin).status_code == 400


class TestArqueoDeCaja:
    def test_el_esperado_suma_las_ventas_en_efectivo(self, client, auth_admin, producto, sin_iva):
        caja = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 5000}).json()
        vender(client, auth_admin, producto.id, cantidad=2)  # 2000 en efectivo

        # Declarando exactamente lo esperado, la diferencia es cero
        cerrada = client.put(f"/cajas/{caja['id']}/cerrar", headers=auth_admin, json={
            "monto_final_declarado": 7000,
        }).json()
        assert cerrada["diferencia_calculada"] == 0

    def test_las_devoluciones_en_efectivo_bajan_lo_esperado(self, client, auth_admin, producto, sin_iva):
        """Sin esto el arqueo daba faltante cada vez que había una devolución."""
        caja = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 5000}).json()
        venta = vender(client, auth_admin, producto.id, cantidad=3).json()  # +3000

        client.post(f"/devoluciones/venta/{venta['id']}", headers=auth_admin, json={
            "metodo_devolucion": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1}],  # -1000
        })

        # En el cajón quedan 5000 + 3000 - 1000 = 7000
        cerrada = client.put(f"/cajas/{caja['id']}/cerrar", headers=auth_admin, json={
            "monto_final_declarado": 7000,
        }).json()
        assert cerrada["diferencia_calculada"] == 0

    def test_detecta_un_faltante(self, client, auth_admin, producto, sin_iva):
        caja = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 1000}).json()
        vender(client, auth_admin, producto.id)  # +1000
        cerrada = client.put(f"/cajas/{caja['id']}/cerrar", headers=auth_admin, json={
            "monto_final_declarado": 1800,
        }).json()
        assert cerrada["diferencia_calculada"] == -200

    def test_no_se_abren_dos_cajas_a_la_vez(self, client, auth_admin):
        client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 1000})
        r = client.post("/cajas/abrir", headers=auth_admin, json={"monto_inicial": 500})
        assert r.status_code == 400


class TestCategorias:
    def test_alta_y_listado(self, client, auth_admin):
        assert client.post("/categorias/", headers=auth_admin, json={"nombre": "Bebidas"}).status_code == 201
        nombres = [c["nombre"] for c in client.get("/categorias/", headers=auth_admin).json()]
        assert "Bebidas" in nombres

    def test_no_permite_nombres_repetidos(self, client, auth_admin):
        client.post("/categorias/", headers=auth_admin, json={"nombre": "Bebidas"})
        r = client.post("/categorias/", headers=auth_admin, json={"nombre": "Bebidas"})
        assert r.status_code == 400

    def test_borrar_la_categoria_no_borra_los_productos(self, client, auth_admin, producto, db):
        categoria = client.post("/categorias/", headers=auth_admin, json={"nombre": "Varios"}).json()
        client.put(f"/productos/{producto.id}", headers=auth_admin, json={"categoria_id": categoria["id"]})

        assert client.delete(f"/categorias/{categoria['id']}", headers=auth_admin).status_code == 204

        db.refresh(producto)
        assert producto.categoria_id is None  # queda sin categoría, pero existe

    def test_el_cajero_puede_leerlas_para_filtrar_el_catalogo(self, client, auth_cajero, admin):
        assert client.get("/categorias/", headers=auth_cajero).status_code == 200

    def test_no_se_asigna_una_categoria_que_no_existe(self, client, auth_admin):
        """SQLite no fuerza las claves foráneas: hay que chequearlo a mano."""
        r = client.post("/productos/", headers=auth_admin, json={
            "codigo_barras": "999", "nombre": "x", "precio_venta": 1, "costo": 1,
            "stock_actual": 1, "categoria_id": 4321,
        })
        assert r.status_code == 400

    def test_el_producto_guarda_su_categoria(self, client, auth_admin, producto, db):
        categoria = client.post("/categorias/", headers=auth_admin, json={"nombre": "Limpieza"}).json()
        r = client.put(f"/productos/{producto.id}", headers=auth_admin, json={
            "categoria_id": categoria["id"],
        })
        assert r.status_code == 200
        assert r.json()["categoria_id"] == categoria["id"]
