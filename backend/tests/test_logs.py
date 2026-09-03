"""Descarga de los logs del backend, para no tener que pedirle al dueño del
comercio que busque una carpeta que no sabe que existe."""
import zipfile
from io import BytesIO

from app import logs


class TestZipDeLogs:
    def test_sin_carpeta_de_logs_da_un_zip_vacio(self, tmp_path, monkeypatch):
        """Una instalación recién migrada puede no haber generado logs
        todavía: no tiene que romper, sólo no traer nada."""
        monkeypatch.setattr(logs, "CARPETA", tmp_path / "no-existe")
        contenido = logs.zip_de_logs()
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            assert zf.namelist() == []

    def test_incluye_el_log_actual_y_los_rotados(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logs, "CARPETA", tmp_path)
        (tmp_path / "backend.log").write_text("error de hoy", encoding="utf-8")
        (tmp_path / "backend.log.1").write_text("error de ayer", encoding="utf-8")
        (tmp_path / "otracosa.txt").write_text("no es un log", encoding="utf-8")

        contenido = logs.zip_de_logs()
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            nombres = set(zf.namelist())
            assert nombres == {"backend.log", "backend.log.1"}
            assert zf.read("backend.log").decode("utf-8") == "error de hoy"


class TestEndpoint:
    def test_requiere_sesion(self, client):
        assert client.get("/logs/descargar").status_code == 401

    def test_un_cajero_no_puede_bajar_los_logs(self, client, auth_cajero, admin):
        assert client.get("/logs/descargar", headers=auth_cajero).status_code == 403

    def test_el_admin_baja_un_zip(self, client, auth_admin):
        r = client.get("/logs/descargar", headers=auth_admin)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert "attachment" in r.headers["content-disposition"]
        # Tiene que ser un .zip válido, aunque esté vacío
        with zipfile.ZipFile(BytesIO(r.content)) as zf:
            assert zf.testzip() is None
