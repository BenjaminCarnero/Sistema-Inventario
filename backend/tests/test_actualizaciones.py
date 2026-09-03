"""Chequeo de versión nueva contra GitHub Releases.

Nunca se llama a GitHub de verdad en los tests: se reemplaza `requests.get`
para poder probar los tres casos que importan (hay una nueva, no hay, y
GitHub no contesta) sin depender de la red ni de que el repositorio tenga
algún release publicado.
"""
import requests

from app import actualizaciones


class _RespuestaFalsa:
    def __init__(self, status_code=200, cuerpo=None):
        self.status_code = status_code
        self._cuerpo = cuerpo or {}

    def json(self):
        return self._cuerpo


class TestBuscarDisponible:
    def test_hay_una_version_mas_nueva(self, monkeypatch):
        monkeypatch.setattr(actualizaciones, "VERSION", "0.1.0")
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **k: _RespuestaFalsa(200, {"tag_name": "v0.2.0", "html_url": "https://x/releases/v0.2.0"}),
        )
        r = actualizaciones.buscar_disponible()
        assert r == {
            "version_actual": "0.1.0",
            "version_disponible": "0.2.0",
            "hay_actualizacion": True,
            "url": "https://x/releases/v0.2.0",
        }

    def test_ya_esta_al_dia(self, monkeypatch):
        monkeypatch.setattr(actualizaciones, "VERSION", "0.2.0")
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **k: _RespuestaFalsa(200, {"tag_name": "v0.2.0"}),
        )
        assert actualizaciones.buscar_disponible()["hay_actualizacion"] is False

    def test_una_version_vieja_publicada_no_cuenta_como_actualizacion(self, monkeypatch):
        """Por si algún día se re-publica un tag anterior por error."""
        monkeypatch.setattr(actualizaciones, "VERSION", "0.3.0")
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **k: _RespuestaFalsa(200, {"tag_name": "v0.2.0"}),
        )
        assert actualizaciones.buscar_disponible()["hay_actualizacion"] is False

    def test_sin_releases_publicados_no_revienta(self, monkeypatch):
        """GitHub contesta 404 cuando el repositorio nunca publicó un release."""
        monkeypatch.setattr(requests, "get", lambda *a, **k: _RespuestaFalsa(404))
        r = actualizaciones.buscar_disponible()
        assert r["hay_actualizacion"] is False
        assert r["version_disponible"] is None

    def test_sin_red_no_revienta(self, monkeypatch):
        """El chequeo de actualización nunca puede tirar abajo nada: si GitHub
        no responde, el comercio sigue con la versión que tiene."""
        def _sin_red(*a, **k):
            raise requests.ConnectionError("no hay red")
        monkeypatch.setattr(requests, "get", _sin_red)
        r = actualizaciones.buscar_disponible()
        assert r["hay_actualizacion"] is False

    def test_una_respuesta_sin_tag_no_revienta(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: _RespuestaFalsa(200, {}))
        assert actualizaciones.buscar_disponible()["hay_actualizacion"] is False


class TestEndpoint:
    def test_requiere_sesion(self, client):
        assert client.get("/actualizaciones/disponible").status_code == 401

    def test_un_cajero_no_puede_consultarlo(self, client, admin, auth_cajero):
        assert client.get("/actualizaciones/disponible", headers=auth_cajero).status_code == 403

    def test_el_admin_lo_consulta(self, client, auth_admin, monkeypatch):
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **k: _RespuestaFalsa(200, {"tag_name": "v0.0.1"}),
        )
        r = client.get("/actualizaciones/disponible", headers=auth_admin)
        assert r.status_code == 200
        assert "version_actual" in r.json()
