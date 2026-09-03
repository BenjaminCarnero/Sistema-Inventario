"""El router de impresión, con la impresora real reemplazada por una función
que sólo guarda qué bytes le mandaron: la entrega por red ya se prueba de
verdad (con un socket real) en test_impresora.py, y el formato de los bytes
en test_ticket_escpos.py. Acá lo que importa es que el router arme el ticket
con los datos correctos de la venta guardada y respete la configuración."""
import pytest

from app import models
from app.routers import impresion


def vender(client, auth, producto_id, cantidad=1, metodo="EFECTIVO", **extra):
    body = {
        "metodo_pago": metodo,
        "detalles": [{"producto_id": producto_id, "cantidad": cantidad, "precio_unitario": 1000}],
    }
    body.update(extra)
    return client.post("/ventas/", headers=auth, json=body)


def habilitar_impresora(client, auth, ip="192.168.0.50"):
    return client.put("/configuracion/", headers=auth, json={
        "valores": {"impresora_habilitada": True, "impresora_ip": ip},
    })


@pytest.fixture
def impresora_capturada(monkeypatch):
    """Reemplaza el envío real por uno que guarda lo que le llega, para poder
    revisar el contenido del ticket sin abrir un socket de verdad."""
    llamadas = []

    def _capturar(ip, puerto, datos, timeout_segundos=5.0):
        llamadas.append({"ip": ip, "puerto": puerto, "datos": datos})

    monkeypatch.setattr(impresion.impresora, "enviar", _capturar)
    return llamadas


class TestImprimirVenta:
    def test_requiere_sesion(self, client):
        assert client.post("/impresion/venta/1").status_code == 401

    def test_venta_inexistente_da_404(self, client, auth_admin):
        r = client.post("/impresion/venta/99999", headers=auth_admin)
        assert r.status_code == 404

    def test_con_la_impresora_apagada_avisa_en_vez_de_intentar(self, client, auth_admin, producto, sin_iva):
        venta = vender(client, auth_admin, producto.id).json()
        r = client.post(f"/impresion/venta/{venta['id']}", headers=auth_admin)
        assert r.status_code == 400
        assert "Impresora" in r.json()["detail"] or "impresora" in r.json()["detail"]

    def test_sin_ip_configurada_avisa_502(self, client, auth_admin, producto, sin_iva):
        client.put("/configuracion/", headers=auth_admin, json={"valores": {"impresora_habilitada": True}})
        venta = vender(client, auth_admin, producto.id).json()
        r = client.post(f"/impresion/venta/{venta['id']}", headers=auth_admin)
        assert r.status_code == 502

    def test_imprime_con_los_datos_reales_de_la_venta(self, client, auth_admin, producto, sin_iva, impresora_capturada):
        habilitar_impresora(client, auth_admin)
        venta = vender(client, auth_admin, producto.id, cantidad=2).json()

        r = client.post(f"/impresion/venta/{venta['id']}", headers=auth_admin)

        assert r.status_code == 200
        assert r.json() == {"impreso": True, "venta_id": venta["id"]}
        assert len(impresora_capturada) == 1
        enviado = impresora_capturada[0]
        assert enviado["ip"] == "192.168.0.50"
        assert producto.nombre.encode("cp1252") in enviado["datos"]
        assert "2x".encode("cp1252") in enviado["datos"]

    def test_un_cajero_tambien_puede_imprimir(self, client, auth_admin, auth_cajero, producto, sin_iva, impresora_capturada):
        """Es lo mismo que hoy hace cualquier cajero apretando "Imprimir" en
        el navegador: no es una operación de administrador."""
        habilitar_impresora(client, auth_admin)
        venta = vender(client, auth_cajero, producto.id).json()

        r = client.post(f"/impresion/venta/{venta['id']}", headers=auth_cajero)
        assert r.status_code == 200

    def test_el_descuento_aplicado_aparece_en_el_ticket(self, client, auth_admin, producto, sin_iva, impresora_capturada):
        descuento = client.post("/descuentos/", headers=auth_admin, json={
            "nombre": "Promo test", "tipo": "PORCENTAJE", "valor": 10, "activo": True,
        }).json()
        habilitar_impresora(client, auth_admin)
        venta = vender(client, auth_admin, producto.id, cantidad=1, descuento_id=descuento["id"]).json()

        r = client.post(f"/impresion/venta/{venta['id']}", headers=auth_admin)
        assert r.status_code == 200
        assert "Promo test".encode("cp1252") in impresora_capturada[0]["datos"]


class TestPrevisualizar:
    def test_no_necesita_la_impresora_habilitada(self, client, auth_admin, producto, sin_iva):
        """Sirve justamente para probar el formato sin depender de tener la
        térmica configurada."""
        venta = vender(client, auth_admin, producto.id).json()
        r = client.get(f"/impresion/venta/{venta['id']}/previsualizar", headers=auth_admin)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert producto.nombre.encode("cp1252") in r.content

    def test_venta_inexistente_da_404(self, client, auth_admin):
        assert client.get("/impresion/venta/99999/previsualizar", headers=auth_admin).status_code == 404
