#!/usr/bin/env bash
#
# Genera un certificado propio para poder entrar por HTTPS desde el celular.
#
# Sin HTTPS el navegador no presta la cámara, así que el escáner no funciona
# fuera de la computadora. Este certificado no lo firma nadie conocido: la
# primera vez el celular avisa que el sitio no es de confianza y hay que
# aceptar una vez. A partir de ahí el sitio cuenta como seguro y el escáner
# anda.
#
# Uso, desde la carpeta frontend:
#     bash scripts/generar-certificado.sh
#
# Si cambia la IP de la computadora en la red, hay que volver a correrlo.

set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p certs

# Las IPs privadas del equipo van dentro del certificado: sin eso el navegador
# se queja además de que el nombre no coincide.
#
# Se incluyen todas y no una sola a propósito. Una máquina con Docker, WSL o
# Hyper-V tiene varias placas virtuales, y adivinar cuál es "la buena" sale
# mal: la primera que aparece suele ser la virtual, no la de la red de casa.
detectar_ips() {
  if command -v ipconfig >/dev/null 2>&1; then
    ipconfig | grep -i "IPv4" | grep -oE "([0-9]{1,3}\.){3}[0-9]{1,3}"
  else
    hostname -I 2>/dev/null | tr ' ' '\n'
  fi | grep -E "^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)" | sort -u
}

IPS="$(detectar_ips || true)"
ALT="DNS:localhost,IP:127.0.0.1"
if [ -z "$IPS" ]; then
  echo "No se detectó ninguna IP de red; el certificado va a servir sólo para localhost."
else
  echo "IPs incluidas en el certificado:"
  for ip in $IPS; do
    echo "  - $ip"
    ALT="$ALT,IP:$ip"
  done
fi

# MSYS_NO_PATHCONV: en Git Bash sobre Windows, el "/CN=..." se toma por una
# ruta y se reescribe como "C:/Program Files/Git/CN=...". En Linux y macOS la
# variable no existe y se ignora sin efecto.
MSYS_NO_PATHCONV=1 \
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 825 \
  -keyout certs/dev.key \
  -out certs/dev.crt \
  -subj "/CN=APPLIFY POS (desarrollo)" \
  -addext "subjectAltName=$ALT" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"

echo
echo "Listo. Certificado en frontend/certs/ (no se sube al repositorio)."
echo "Levantá el servidor con 'npm run dev' y entrá desde el celular a:"
for ip in $IPS; do echo "    https://$ip:5173"; done
