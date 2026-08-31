"""Sesiones revocables, ruteo de la API y ventas que llegan tarde.

Todo lo que hay acá cubre un agujero que existió de verdad y que se cerró.
Si alguno de estos tests se pone en rojo, es que volvió.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import main, models
from app.config import settings
from tests.conftest import cabecera, crear_usuario, token_de


# --- Identidad de la sesión ------------------------------------------------
class TestIdentidadDelToken:
    """El token identifica por id y no por nombre.

    Identificando por nombre alcanzaba con que un administrador renombrara al
    cajero `juan` y creara después otro usuario `juan` con rol ADMIN: la sesión
    que el cajero ya tenía abierta pasaba a resolver al administrador nuevo.
    No hacía falta ningún atacante, sólo dos operaciones permitidas.
    """

    def test_renombrar_y_reusar_el_nombre_no_asciende_a_nadie(self, client, db, admin):
        cajero = crear_usuario(db, "juan", "juan1234", models.RolEnum.CAJERO.value)
        tok_cajero = cabecera(token_de(client, "juan", "juan1234"))
        tok_admin = cabecera(token_de(client, "admin", "admin123"))

        assert client.get("/auth/users", headers=tok_cajero).status_code == 403

        r = client.put(
            f"/auth/users/{cajero.id}",
            json={"nombre": "juan.perez", "rol_id": 3, "estado": True},
            headers=tok_admin,
        )
        assert r.status_code == 200, r.text

        r = client.post(
            "/auth/register",
            json={"nombre": "juan", "pin_acceso": "supersecreto", "rol_id": 1, "estado": True},
            headers=tok_admin,
        )
        assert r.status_code == 201, r.text

        # El token viejo sigue siendo el del cajero, no el del admin nuevo
        assert client.get("/auth/users", headers=tok_cajero).status_code == 403

    def test_no_se_pueden_repetir_nombres_de_usuario(self, db):
        """La unicidad la fuerza la base, no sólo el chequeo del router."""
        from sqlalchemy.exc import IntegrityError

        crear_usuario(db, "repetido", "12345678", models.RolEnum.CAJERO.value)
        with pytest.raises(IntegrityError):
            crear_usuario(db, "repetido", "87654321", models.RolEnum.ADMIN.value)
        db.rollback()

    def test_un_token_del_formato_viejo_no_sirve(self, client, db, admin):
        """Los tokens que traen el nombre en `sub` son los del agujero anterior."""
        viejo = jwt.encode(
            {
                "sub": "admin",
                "rol": models.RolEnum.ADMIN.value,
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        assert client.get("/auth/users", headers=cabecera(viejo)).status_code == 401


class TestRevocacionDeSesiones:
    """Cambiar un PIN saca de circulación las sesiones abiertas con el viejo.

    Antes no: el endpoint decía servir para eso y el token anterior seguía
    valiendo hasta doce horas más. Un PIN visto por encima del hombro no se
    podía cerrar de ninguna manera.
    """

    def test_cambiar_el_pin_propio_corta_la_sesion(self, client, db, admin):
        tok = cabecera(token_de(client, "admin", "admin123"))
        assert client.get("/auth/users", headers=tok).status_code == 200

        r = client.put(
            "/auth/me/pin",
            json={"pin_actual": "admin123", "pin_nuevo": "otroPIN12345"},
            headers=tok,
        )
        assert r.status_code == 204, r.text

        assert client.get("/auth/users", headers=tok).status_code == 401
        # Y con el PIN nuevo se vuelve a entrar sin problema
        assert client.get(
            "/auth/users", headers=cabecera(token_de(client, "admin", "otroPIN12345"))
        ).status_code == 200

    def test_reiniciar_el_pin_de_otro_corta_su_sesion(self, client, db, admin):
        victima = crear_usuario(db, "victima", "victima123", models.RolEnum.ENCARGADO.value)
        tok_victima = cabecera(token_de(client, "victima", "victima123"))
        tok_admin = cabecera(token_de(client, "admin", "admin123"))

        assert client.get("/stock/movimientos", headers=tok_victima).status_code == 200

        r = client.put(
            f"/auth/users/{victima.id}/pin",
            json={"pin_nuevo": "nuevoPIN123"},
            headers=tok_admin,
        )
        assert r.status_code == 204, r.text

        assert client.get("/stock/movimientos", headers=tok_victima).status_code == 401

    def test_la_baja_sigue_cortando_la_sesion(self, client, db, admin):
        """Contraste: esto ya andaba y tiene que seguir andando."""
        otro = crear_usuario(db, "otro", "otro1234", models.RolEnum.CAJERO.value)
        tok = cabecera(token_de(client, "otro", "otro1234"))
        client.delete(
            f"/auth/users/{otro.id}",
            headers=cabecera(token_de(client, "admin", "admin123")),
        )
        assert client.get("/productos/", headers=tok).status_code == 400


# --- Frenos ----------------------------------------------------------------
class TestFrenoDePeticiones:
    """Techo general por IP, aparte del freno del login.

    Publicado en internet, cualquiera con la URL puede martillar la API hasta
    que la caja deje de responder. Un cliente con un bucle roto hace lo mismo
    sin mala intención.
    """

    @pytest.fixture
    def con_freno(self, monkeypatch):
        # La suite lo corre apagado (ver conftest): acá se enciende a mano y se
        # limpia el contador, que vive en memoria del proceso.
        monkeypatch.setattr(settings, "LIMITE_PETICIONES_POR_MINUTO", 5)
        main._peticiones_por_ip.clear()
        yield
        main._peticiones_por_ip.clear()

    def test_pasado_el_techo_se_contesta_429(self, client, db, admin, con_freno):
        tok = cabecera(token_de(client, "admin", "admin123"))
        codigos = [client.get("/productos/", headers=tok).status_code for _ in range(12)]
        assert 429 in codigos, codigos
        assert codigos[0] == 200, "las primeras tienen que pasar"

    def test_health_nunca_se_frena(self, client, con_freno):
        """El POS lo consulta cada 15 s para saber si hay servidor.

        Frenarlo sería apagar el aviso de "sin conexión" justo cuando hay
        problemas.
        """
        assert all(client.get("/health").status_code == 200 for _ in range(30))


class TestIpDetrasDeProxy:
    """De dónde se saca la IP que usan los frenos."""

    def test_sin_proxy_configurado_no_se_cree_la_cabecera(self, client, db, admin, monkeypatch):
        """`X-Forwarded-For` la puede inventar cualquiera."""
        from app import red

        monkeypatch.setattr(settings, "PROXIES_CONFIABLES", 0)

        class PedidoFalso:
            headers = {"x-forwarded-for": "1.2.3.4"}
            client = type("C", (), {"host": "10.0.0.9"})()

        assert red.ip_del_cliente(PedidoFalso()) == "10.0.0.9"

    def test_con_un_proxy_se_toma_la_entrada_que_el_escribio(self, monkeypatch):
        """El cliente puede inventar la izquierda de la cadena, no la derecha.

        Con `X-Forwarded-For: 1.2.3.4` inventado por el cliente, nuestro proxy
        agrega al final la IP real: queda `1.2.3.4, 200.1.1.1`.
        """
        from app import red

        monkeypatch.setattr(settings, "PROXIES_CONFIABLES", 1)

        class PedidoFalso:
            headers = {"x-forwarded-for": "1.2.3.4, 200.1.1.1"}
            client = type("C", (), {"host": "10.0.0.9"})()

        assert red.ip_del_cliente(PedidoFalso()) == "200.1.1.1"


# --- Ruteo -----------------------------------------------------------------
class TestLaApiTieneSus404:
    """Servir el frontend desde el backend se había comido todos los 404.

    `GET /ventas/cualquier-cosa` contestaba 200 con HTML: la API entera perdió
    sus 404, el cliente necesitó una función para adivinar cuándo "el backend
    no conoce esta ruta", y cualquier monitoreo que busque sondeos por sus 404
    quedaba ciego.
    """

    def test_una_ruta_de_api_inexistente_es_404_json(self, client, db, admin):
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = client.get("/ventas/no-existe-esta-ruta", headers=tok)
        assert r.status_code == 404
        assert "json" in r.headers.get("content-type", "")

    def test_un_prefijo_parecido_no_cuenta_como_api(self, client):
        """`/ventasfalsas` empieza con `/ventas` y no es una ruta de la API."""
        assert main.es_ruta_de_api("/ventas") is True
        assert main.es_ruta_de_api("/ventas/1") is True
        assert main.es_ruta_de_api("/ventasfalsas") is False


# --- La venta que llega tarde ----------------------------------------------
class TestHoraDeLaVentaOffline:
    """Una venta cobrada sin señal conserva la hora en que se cobró.

    El POS ya guardaba `fecha_hora_local` en su cola pero no la mandaba, así
    que la venta quedaba fechada cuando se sincronizó: un corte de internet el
    viernes a la tarde movía todas esas ventas al sábado, y tanto el arqueo del
    viernes como el del sábado quedaban mal.
    """

    def _vender(self, client, tok, producto, **extra):
        cuerpo = {
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }
        cuerpo.update(extra)
        return client.post("/ventas/", json=cuerpo, headers=tok)

    def test_se_respeta_la_hora_declarada_por_el_pos(self, client, db, admin, producto, sin_iva):
        tok = cabecera(token_de(client, "admin", "admin123"))
        ayer = datetime.now(timezone.utc) - timedelta(days=1)

        r = self._vender(client, tok, producto,
                         uuid_cliente="de-ayer", fecha_hora_local=ayer.isoformat())
        assert r.status_code == 201, r.text

        guardada = db.query(models.Venta).filter(
            models.Venta.uuid_cliente == "de-ayer"
        ).first().fecha_hora
        esperada = ayer.replace(tzinfo=None)
        assert abs((guardada - esperada).total_seconds()) < 5

    def test_una_fecha_futura_no_se_acepta(self, client, db, admin, producto, sin_iva):
        """Un reloj adelantado metería la venta en el arqueo de mañana."""
        tok = cabecera(token_de(client, "admin", "admin123"))
        futuro = datetime.now(timezone.utc) + timedelta(days=2)

        r = self._vender(client, tok, producto,
                         uuid_cliente="del-futuro", fecha_hora_local=futuro.isoformat())
        assert r.status_code == 201

        guardada = db.query(models.Venta).filter(
            models.Venta.uuid_cliente == "del-futuro"
        ).first().fecha_hora
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((guardada - ahora).total_seconds()) < 60

    def test_una_fecha_absurdamente_vieja_no_se_acepta(self, client, db, admin, producto, sin_iva):
        """Más probable que el reloj del equipo esté mal a que la venta sea de 2019."""
        tok = cabecera(token_de(client, "admin", "admin123"))
        viejisima = datetime.now(timezone.utc) - timedelta(days=400)

        r = self._vender(client, tok, producto,
                         uuid_cliente="prehistorica", fecha_hora_local=viejisima.isoformat())
        assert r.status_code == 201

        guardada = db.query(models.Venta).filter(
            models.Venta.uuid_cliente == "prehistorica"
        ).first().fecha_hora
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((guardada - ahora).total_seconds()) < 60

    def test_sin_fecha_declarada_manda_la_del_servidor(self, client, db, admin, producto, sin_iva):
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = self._vender(client, tok, producto, uuid_cliente="sin-fecha")
        assert r.status_code == 201

        guardada = db.query(models.Venta).filter(
            models.Venta.uuid_cliente == "sin-fecha"
        ).first().fecha_hora
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((guardada - ahora).total_seconds()) < 60


class TestDivergenciaDeTotal:
    """El ticket puede no coincidir con lo que el servidor recalcula.

    El POS cobra sin señal con el catálogo que tiene guardado. Si el precio
    cambió mientras tanto, el cliente se llevó un ticket por un importe y el
    sistema guarda otro. El total que vale sigue siendo el del servidor —esa
    regla no se toca—, pero la diferencia tiene que quedar registrada.
    """

    def _vender(self, client, tok, producto, total_cobrado):
        return client.post("/ventas/", json={
            "metodo_pago": "EFECTIVO",
            "uuid_cliente": f"div-{total_cobrado}",
            "total_cobrado": total_cobrado,
            "detalles": [{"producto_id": producto.id, "cantidad": 1, "precio_unitario": 1000}],
        }, headers=tok)

    def test_manda_el_total_del_servidor(self, client, db, admin, producto, sin_iva):
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = self._vender(client, tok, producto, total_cobrado=800.0)
        assert r.status_code == 201
        assert r.json()["total"] == 1000.0

    def test_la_diferencia_queda_auditada(self, client, db, admin, producto, sin_iva):
        tok = cabecera(token_de(client, "admin", "admin123"))
        self._vender(client, tok, producto, total_cobrado=800.0)

        entradas = db.query(models.Auditoria).filter(
            models.Auditoria.entidad == "venta"
        ).all()
        assert len(entradas) == 1
        assert "800.00" in entradas[0].valor_anterior
        assert "1000.00" in entradas[0].valor_nuevo

    def test_sin_diferencia_no_se_ensucia_la_auditoria(self, client, db, admin, producto, sin_iva):
        tok = cabecera(token_de(client, "admin", "admin123"))
        self._vender(client, tok, producto, total_cobrado=1000.0)
        assert db.query(models.Auditoria).filter(
            models.Auditoria.entidad == "venta"
        ).count() == 0


# --- Stock ------------------------------------------------------------------
class TestElStockSiempreDejaRastro:
    def test_no_se_puede_mover_el_stock_editando_el_producto(
        self, client, db, admin, producto
    ):
        """Era el hueco por el que se tapa un faltante.

        Contar mal, corregir el número a mano desde la pantalla de productos, y
        que el historial de stock no muestre absolutamente nada.
        """
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = client.put(f"/productos/{producto.id}", json={"stock_actual": 9999}, headers=tok)
        assert r.status_code == 200

        db.expire_all()
        assert db.get(models.Producto, producto.id).stock_actual == 100

    def test_el_camino_correcto_sigue_andando(self, client, db, admin, producto):
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = client.post("/stock/movimientos", headers=tok, json={
            "producto_id": producto.id, "tipo_movimiento": "AJUSTE",
            "cantidad": 9999, "motivo": "Recuento",
        })
        assert r.status_code == 201
        db.expire_all()
        assert db.get(models.Producto, producto.id).stock_actual == 9999
        assert db.query(models.MovimientoStock).count() == 1


class TestEscriturasConcurrentesDeStock:
    """El stock se mueve con UPDATE relativos y no leyendo y sumando en Python.

    `with_for_update()` no hace nada en SQLite —compila a un SELECT pelado—, así
    que el patrón leer-modificar-escribir pierde una de dos escrituras
    simultáneas sin dar ningún error.
    """

    def _sql_de_stock(self, bloque):
        from sqlalchemy import event
        from app.database import engine

        sentencias = []

        def escuchar(conn, cursor, statement, parameters, context, executemany):
            if "UPDATE productos" in statement:
                sentencias.append(statement.replace("\n", " "))

        event.listen(engine, "before_cursor_execute", escuchar)
        try:
            bloque()
        finally:
            event.remove(engine, "before_cursor_execute", escuchar)
        return sentencias

    def _es_relativo(self, sentencias):
        return any("stock_actual +" in s or "stock_actual -" in s for s in sentencias)

    def test_la_devolucion_repone_con_update_relativo(
        self, client, db, admin, producto, sin_iva
    ):
        tok = cabecera(token_de(client, "admin", "admin123"))
        venta = client.post("/ventas/", headers=tok, json={
            "metodo_pago": "EFECTIVO",
            "detalles": [{"producto_id": producto.id, "cantidad": 5, "precio_unitario": 1000}],
        }).json()

        def devolver():
            r = client.post(f"/devoluciones/venta/{venta['id']}", headers=tok, json={
                "motivo": "prueba", "metodo_devolucion": "EFECTIVO",
                "detalles": [{"producto_id": producto.id, "cantidad": 2}],
            })
            assert r.status_code == 201, r.text

        sentencias = self._sql_de_stock(devolver)
        assert self._es_relativo(sentencias), sentencias
        db.expire_all()
        assert db.get(models.Producto, producto.id).stock_actual == 97

    def test_recibir_un_pedido_suma_con_update_relativo(self, client, db, admin, producto):
        tok = cabecera(token_de(client, "admin", "admin123"))
        prov = client.post("/proveedores/", json={"nombre": "Prov 1"}, headers=tok).json()
        pedido = client.post("/pedidos/", headers=tok, json={
            "proveedor_id": prov["id"],
            "detalles": [{"producto_id": producto.id, "cantidad": 10}],
        }).json()

        def recibir():
            r = client.post(f"/pedidos/{pedido['id']}/recibir", headers=tok, json={
                "detalles": [{"producto_id": producto.id, "cantidad_recibida": 10}],
            })
            assert r.status_code == 200, r.text

        sentencias = self._sql_de_stock(recibir)
        assert self._es_relativo(sentencias), sentencias
        db.expire_all()
        assert db.get(models.Producto, producto.id).stock_actual == 110


# --- Catálogo ---------------------------------------------------------------
class TestBajaDeProductos:
    """Un producto discontinuado tiene que poder salir del catálogo.

    No se borra —las ventas pasadas lo referencian— pero hasta ahora tampoco
    había forma de darlo de baja: el catálogo del POS sólo podía crecer.
    """

    def test_se_da_de_baja_y_desaparece_del_catalogo(self, client, db, admin, producto):
        tok = cabecera(token_de(client, "admin", "admin123"))
        assert len(client.get("/productos/catalogo", headers=tok).json()) == 1

        assert client.delete(f"/productos/{producto.id}", headers=tok).status_code == 204

        assert client.get("/productos/catalogo", headers=tok).json() == []
        # Pero el registro sigue existiendo
        assert db.get(models.Producto, producto.id) is not None

    def test_la_baja_queda_auditada(self, client, db, admin, producto):
        tok = cabecera(token_de(client, "admin", "admin123"))
        client.delete(f"/productos/{producto.id}", headers=tok)

        entrada = db.query(models.Auditoria).filter(
            models.Auditoria.entidad == "producto",
            models.Auditoria.accion == "ELIMINAR",
        ).first()
        assert entrada is not None
        assert entrada.entidad_id == producto.id

    def test_el_backoffice_puede_verlos_si_los_pide(self, client, db, admin, producto):
        tok = cabecera(token_de(client, "admin", "admin123"))
        client.delete(f"/productos/{producto.id}", headers=tok)

        assert client.get("/productos/", headers=tok).json() == []
        assert len(client.get("/productos/?incluir_inactivos=true", headers=tok).json()) == 1

    def test_no_se_da_de_baja_dos_veces(self, client, db, admin, producto):
        tok = cabecera(token_de(client, "admin", "admin123"))
        client.delete(f"/productos/{producto.id}", headers=tok)
        assert client.delete(f"/productos/{producto.id}", headers=tok).status_code == 400

    def test_un_cajero_no_puede_dar_de_baja(self, client, db, cajero, producto):
        tok = cabecera(token_de(client, "cajero", "cajero123"))
        assert client.delete(f"/productos/{producto.id}", headers=tok).status_code == 403


class TestZonaHorariaDelComercio:
    """Dónde empieza y termina "el día" para los arqueos y los reportes.

    Sin configurar se usa el reloj del servidor, que está bien cuando el
    servidor está en el mostrador. Deja de estarlo apenas se hostea: un VPS en
    UTC corta el día a las 21:00 hora argentina, justo en el horario en que más
    se vende, y esas ventas caen en el reporte del día siguiente.
    """

    def test_el_dia_local_se_calcula_con_la_zona_configurada(self, monkeypatch):
        from datetime import date

        from app import fechas

        monkeypatch.setattr(settings, "ZONA_HORARIA", "America/Argentina/Buenos_Aires")
        inicio, fin = fechas.rango_local_en_utc(date(2026, 3, 10), date(2026, 3, 10))

        # Buenos Aires es UTC-3: el día del local arranca a las 03:00 UTC
        assert inicio.hour == 3
        assert (fin - inicio).days == 1

    def test_otra_zona_da_otro_corte(self, monkeypatch):
        from datetime import date

        from app import fechas

        monkeypatch.setattr(settings, "ZONA_HORARIA", "UTC")
        inicio, _ = fechas.rango_local_en_utc(date(2026, 3, 10), date(2026, 3, 10))
        assert inicio.hour == 0

    def test_una_zona_mal_escrita_no_tumba_el_sistema(self, monkeypatch):
        """Se sigue con la del servidor: es el comportamiento de siempre."""
        from app import fechas

        monkeypatch.setattr(settings, "ZONA_HORARIA", "Marte/Olympus_Mons")
        assert fechas.zona_del_comercio() is None

    def test_sin_configurar_manda_el_reloj_del_servidor(self, monkeypatch):
        from app import fechas

        monkeypatch.setattr(settings, "ZONA_HORARIA", "")
        assert fechas.zona_del_comercio() is None


class TestRestaurarConfiguracion:
    def test_volver_a_fabrica_deja_auditoria(self, client, db, admin):
        """Se podía volver el IVA y el tope de devolución a los valores de
        fábrica sin que quedara rastro de quién lo hizo."""
        tok = cabecera(token_de(client, "admin", "admin123"))
        client.put("/configuracion/", headers=tok, json={"valores": {"iva_porcentaje": 10.5}})

        antes = db.query(models.Auditoria).filter(
            models.Auditoria.entidad == "configuracion"
        ).count()

        assert client.post("/configuracion/restaurar", headers=tok).status_code == 200

        despues = db.query(models.Auditoria).filter(
            models.Auditoria.entidad == "configuracion"
        ).count()
        assert despues > antes
