"""El router de Mercado Pago.

La lógica de negocio del cobro por QR —que el total lo pone el servidor, que
una referencia respalda una sola venta— ya se prueba en
`test_seguridad_avanzada.TestCobroPorQR`, reemplazando `total_aprobado`.

Lo que no se probaba nunca es este router: cómo se lee la respuesta del SDK,
qué pasa cuando no hay token configurado, y que el endpoint de estado no sirva
para dar una venta por cobrada. Es la parte del camino del dinero que depende
de un tercero, así que es la que más conviene tener fijada: el día que Mercado
Pago cambie la forma de la respuesta, esto se pone en rojo acá y no en la caja
de un comercio.
"""
import pytest

from app.config import settings
from app.routers import pagos
from tests.conftest import cabecera, token_de


class _Pagos:
    def __init__(self, resultados):
        self._resultados = resultados
        self.ultima_busqueda = None

    def search(self, filtros, request_options=None):
        self.ultima_busqueda = (filtros, request_options)
        return {"response": {"results": self._resultados}}


class _Preferencias:
    def __init__(self):
        self.ultimo_cuerpo = None

    def create(self, datos):
        self.ultimo_cuerpo = datos
        return {"response": {"init_point": "https://mp.example/checkout/abc"}}


class SdkFalso:
    """Lo mínimo del SDK que usa el router."""

    def __init__(self, resultados=()):
        self._pagos = _Pagos(list(resultados))
        self._preferencias = _Preferencias()

    def payment(self):
        return self._pagos

    def preference(self):
        return self._preferencias


@pytest.fixture
def sdk(monkeypatch):
    """Reemplaza el SDK. Devuelve una función para fijar los pagos que existen."""
    creado = {}

    def instalar(resultados=()):
        creado["sdk"] = SdkFalso(resultados)
        monkeypatch.setattr(pagos, "get_sdk", lambda: creado["sdk"])
        return creado["sdk"]

    instalar()
    return instalar


# --- Lectura de la respuesta de Mercado Pago -------------------------------
class TestTotalAprobado:
    def test_suma_solo_los_aprobados(self, sdk):
        """Un pago rechazado o pendiente no cuenta como cobrado."""
        sdk([
            {"status": "approved", "transaction_amount": 600},
            {"status": "rejected", "transaction_amount": 5000},
            {"status": "pending", "transaction_amount": 400},
            {"status": "approved", "transaction_amount": 400},
        ])
        assert pagos.total_aprobado("ref-1") == 1000

    def test_varios_pagos_de_la_misma_referencia_se_suman(self, sdk):
        """El cliente que paga en dos partes, o que reintenta tras un rechazo."""
        sdk([
            {"status": "approved", "transaction_amount": 300},
            {"status": "approved", "transaction_amount": 700},
        ])
        assert pagos.total_aprobado("ref-1") == 1000

    def test_sin_pagos_da_cero(self, sdk):
        sdk([])
        assert pagos.total_aprobado("ref-inexistente") == 0

    def test_un_importe_que_falta_o_es_nulo_no_rompe(self, sdk):
        """La respuesta viene de afuera: no se asume que traiga todo."""
        sdk([
            {"status": "approved"},
            {"status": "approved", "transaction_amount": None},
            {"status": "approved", "transaction_amount": "250.50"},
        ])
        assert pagos.total_aprobado("ref-1") == 250.50

    def test_la_consulta_no_se_queda_colgada(self, sdk):
        """`POST /ventas` consulta esto con la transacción de escritura abierta.

        Con la espera que trae el SDK por defecto —60 s y tres reintentos— eso
        son hasta tres minutos de base bloqueada para las otras cajas.
        """
        falso = sdk([])
        pagos.total_aprobado("ref-1")
        _, opciones = falso.payment().ultima_busqueda
        assert opciones is pagos.ESPERA_CONSULTA
        assert pagos.ESPERA_CONSULTA.connection_timeout <= 10
        assert pagos.ESPERA_CONSULTA.max_retries == 0

    def test_se_busca_por_la_referencia_pedida(self, sdk):
        falso = sdk([])
        pagos.total_aprobado("ref-buscada")
        filtros, _ = falso.payment().ultima_busqueda
        assert filtros == {"external_reference": "ref-buscada"}


class TestAlcanza:
    def test_el_importe_justo_alcanza(self):
        assert pagos.alcanza(1000.0, 1000.0)

    def test_un_centavo_de_menos_se_tolera(self):
        """Mercado Pago redondea a dos decimales."""
        assert pagos.alcanza(999.99, 1000.0)

    def test_pagar_de_menos_no_alcanza(self):
        assert not pagos.alcanza(900.0, 1000.0)

    def test_pagar_de_mas_alcanza(self):
        assert pagos.alcanza(1200.0, 1000.0)


# --- Sin integración configurada -------------------------------------------
class TestSinTokenConfigurado:
    def test_se_avisa_con_503_y_no_se_rompe_el_arranque(self, monkeypatch):
        """La integración es opcional: sin token la API tiene que seguir viva."""
        monkeypatch.setattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "")
        with pytest.raises(Exception) as error:
            pagos.get_sdk()
        assert getattr(error.value, "status_code", None) == 503

    def test_el_endpoint_de_estado_contesta_503(self, client, db, admin, monkeypatch):
        monkeypatch.setattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "")
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = client.get("/pagos/mercadopago/status/ref-1?total_esperado=1000", headers=tok)
        assert r.status_code == 503


# --- Endpoints -------------------------------------------------------------
class TestEstadoDelCobro:
    def test_hace_falta_estar_logueado(self, client, db, admin, sdk):
        assert client.get(
            "/pagos/mercadopago/status/ref-1?total_esperado=1000"
        ).status_code == 401

    def test_avisa_cuando_esta_acreditado(self, client, db, admin, sdk):
        sdk([{"status": "approved", "transaction_amount": 1000}])
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = client.get("/pagos/mercadopago/status/ref-1?total_esperado=1000", headers=tok)
        assert r.status_code == 200
        assert r.json()["approved"] is True

    def test_avisa_cuando_pagaron_de_menos(self, client, db, admin, sdk):
        """Se pagó algo pero no alcanza: el cajero tiene que enterarse en vez de
        quedarse mirando una pantalla que gira."""
        sdk([{"status": "approved", "transaction_amount": 400}])
        tok = cabecera(token_de(client, "admin", "admin123"))
        r = client.get("/pagos/mercadopago/status/ref-1?total_esperado=1000", headers=tok)
        cuerpo = r.json()
        assert cuerpo["approved"] is False
        assert cuerpo["monto_insuficiente"] is True
        assert cuerpo["pagado"] == 400

    def test_sin_pagos_no_dice_que_falta_plata(self, client, db, admin, sdk):
        """Todavía no pagó nada: no es "pagó de menos", es que no pagó."""
        sdk([])
        tok = cabecera(token_de(client, "admin", "admin123"))
        cuerpo = client.get(
            "/pagos/mercadopago/status/ref-1?total_esperado=1000", headers=tok
        ).json()
        assert cuerpo == {"approved": False, "pagado": 0.0}

    def test_un_total_esperado_invalido_se_rechaza(self, client, db, admin, sdk):
        tok = cabecera(token_de(client, "admin", "admin123"))
        assert client.get(
            "/pagos/mercadopago/status/ref-1?total_esperado=0", headers=tok
        ).status_code == 422

    def test_este_endpoint_no_registra_ninguna_venta(self, client, db, admin, producto, sdk):
        """Es sólo un aviso para la pantalla.

        Tanto la referencia como el total los elige quien llama, así que si esto
        cerrara ventas alcanzaría con pedirlo con los números convenientes. La
        confirmación que vale es la de `POST /ventas`.
        """
        from app import models

        sdk([{"status": "approved", "transaction_amount": 999_999}])
        tok = cabecera(token_de(client, "admin", "admin123"))
        client.get("/pagos/mercadopago/status/ref-1?total_esperado=1", headers=tok)
        assert db.query(models.Venta).count() == 0


class TestCrearPreferencia:
    def test_devuelve_una_referencia_propia_por_cobro(self, client, db, admin, sdk):
        """La referencia la genera el servidor y no el cliente: es lo que
        después ata el pago a una venta y sólo a una."""
        tok = cabecera(token_de(client, "admin", "admin123"))
        cuerpo = {"title": "Compra", "quantity": 1, "unit_price": 1500.0}

        primera = client.post("/pagos/mercadopago/preference", headers=tok, json=cuerpo).json()
        segunda = client.post("/pagos/mercadopago/preference", headers=tok, json=cuerpo).json()

        assert primera["init_point"].startswith("https://")
        assert primera["external_reference"] != segunda["external_reference"]

    def test_hace_falta_estar_logueado(self, client, db, admin, sdk):
        assert client.post("/pagos/mercadopago/preference", json={
            "title": "Compra", "quantity": 1, "unit_price": 100.0,
        }).status_code == 401

    @pytest.mark.parametrize("cuerpo", [
        {"title": "", "quantity": 1, "unit_price": 100.0},
        {"title": "Compra", "quantity": 0, "unit_price": 100.0},
        {"title": "Compra", "quantity": -3, "unit_price": 100.0},
        {"title": "Compra", "quantity": 1, "unit_price": 0},
        {"title": "Compra", "quantity": 1, "unit_price": -100.0},
        {"title": "Compra", "quantity": 99_999_999, "unit_price": 100.0},
    ])
    def test_no_viaja_cualquier_cosa_a_mercado_pago(self, client, db, admin, sdk, cuerpo):
        """Sin techos, un importe negativo o absurdo se manda tal cual."""
        tok = cabecera(token_de(client, "admin", "admin123"))
        assert client.post(
            "/pagos/mercadopago/preference", headers=tok, json=cuerpo
        ).status_code == 422

    def test_el_comprador_vuelve_a_la_direccion_configurada(self, client, db, admin, sdk):
        """Clavado a localhost, el que paga desde su celular termina en una
        página que sólo existe en la máquina de la caja."""
        falso = sdk()
        tok = cabecera(token_de(client, "admin", "admin123"))
        client.post("/pagos/mercadopago/preference", headers=tok, json={
            "title": "Compra", "quantity": 1, "unit_price": 100.0,
        })

        enviado = falso.preference().ultimo_cuerpo
        assert enviado["back_urls"]["success"] == settings.FRONTEND_URL
        assert enviado["external_reference"]
