"""No hay hardware para probar esto de verdad, pero el envío por red no
necesita hardware: es un socket TCP común. Se levanta un servidor de mentira
en localhost y se verifica, byte a byte, lo que llegaría a una impresora
real — es la parte de la impresión térmica que sí se puede probar sin comprar
nada."""
import socket
import threading

import pytest

from app import impresora


class ImpresoraFalsa:
    """Un servidor TCP que junta lo que le mandan, como haría el firmware de
    la impresora del lado de adentro del puerto 9100."""

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(1)
        self.ip, self.puerto = self.socket.getsockname()
        self.recibido = b""
        self._hilo = threading.Thread(target=self._atender, daemon=True)
        self._hilo.start()

    def _atender(self):
        try:
            conexion, _ = self.socket.accept()
        except OSError:
            return
        with conexion:
            while True:
                trozo = conexion.recv(4096)
                if not trozo:
                    break
                self.recibido += trozo

    def cerrar(self):
        self.socket.close()
        self._hilo.join(timeout=2)


@pytest.fixture
def impresora_falsa():
    server = ImpresoraFalsa()
    yield server
    server.cerrar()


class TestEnviar:
    def test_manda_exactamente_los_bytes_que_se_le_dan(self, impresora_falsa):
        datos = b"\x1b@Hola, ticket\n\x1dV\x01"
        impresora.enviar(impresora_falsa.ip, impresora_falsa.puerto, datos)
        impresora_falsa.cerrar()  # fuerza el flush del hilo lector
        assert impresora_falsa.recibido == datos

    def test_sin_ip_configurada_avisa_sin_intentar_conectar(self):
        with pytest.raises(impresora.ErrorDeImpresion, match="No hay una impresora configurada"):
            impresora.enviar("", 9100, b"algo")

    def test_puerto_cerrado_da_un_error_legible(self):
        """Un puerto sin nadie escuchando debería rechazar la conexión al
        toque, pero no en todos los entornos: en esta misma máquina, sin
        firewall raro de por medio, terminó en timeout en vez de "conexión
        rechazada" — Windows no siempre manda el RST que se esperaría. Los dos
        caminos terminan en el mismo ErrorDeImpresion, así que el test acepta
        cualquiera de los dos mensajes en vez de asumir cuál va a pasar."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        _, puerto_libre = sock.getsockname()
        sock.close()  # el puerto queda libre y sin nadie escuchando

        with pytest.raises(impresora.ErrorDeImpresion, match="No se pudo conectar|no contestó a tiempo"):
            impresora.enviar("127.0.0.1", puerto_libre, b"algo", timeout_segundos=2)

    def test_ip_inalcanzable_da_timeout_legible(self):
        """10.255.255.1 es una IP privada que normalmente no responde: sirve
        para probar el mensaje de timeout sin depender de que exista de
        verdad una impresora apagada en la red."""
        with pytest.raises(impresora.ErrorDeImpresion, match="no contestó a tiempo|No se pudo conectar"):
            impresora.enviar("10.255.255.1", 9100, b"algo", timeout_segundos=1)
