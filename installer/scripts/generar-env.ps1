<#
    .SINOPSIS
    Genera backend\.env para una instalación nueva, pidiendo por consola lo
    que no se puede adivinar: la zona horaria del comercio y la dirección
    pública del servidor. El nombre del comercio y el primer administrador
    NO se piden acá — eso lo resuelve el asistente de primer arranque que
    aparece en el propio POS la primera vez que se abre en el navegador
    (ver GET /auth/estado-inicial en backend/app/routers/auth.py).

    .DESCRIPCION
    Pensado para correr una sola vez, como parte del instalador (Inno Setup
    lo llama después de copiar los archivos y antes de instalar el servicio).
    También se puede correr a mano para reinstalar o para regenerar el .env
    en un equipo ya instalado.

    Si backend\.env ya existe, no lo pisa sin confirmación: perder la
    SECRET_KEY cierra todas las sesiones abiertas, y perder RESPALDO_EXTERNO
    hace que las copias vuelvan a quedar sólo en este disco sin que nadie se
    entere.

    .PARAMETRO CarpetaBackend
    Carpeta backend/ de la instalación (donde va a vivir el .env, la base y
    los respaldos). Por defecto, la que está al lado de este script asumiendo
    la estructura de instalación: <raiz>\backend, <raiz>\frontend\dist.

    .PARAMETRO NoInteractivo
    Para pruebas o instalaciones desatendidas: usa los valores pasados por
    parámetro en vez de preguntar, y falla si falta alguno obligatorio en vez
    de quedarse esperando input que nunca va a llegar.
#>
[CmdletBinding()]
param(
    [string]$CarpetaBackend = (Join-Path (Split-Path -Parent $PSScriptRoot) "backend"),
    [string]$ZonaHoraria,
    [string]$DireccionPublica,
    [string]$CarpetaRespaldoExterno,
    [string]$MercadoPagoToken = "",
    [int]$ProxiesConfiables = 0,
    [switch]$NoInteractivo
)

$ErrorActionPreference = "Stop"

function Pedir([string]$Mensaje, [string]$PorDefecto = "") {
    if ($NoInteractivo) { return $PorDefecto }
    $sufijo = if ($PorDefecto) { " [$PorDefecto]" } else { "" }
    $valor = Read-Host "$Mensaje$sufijo"
    if ([string]::IsNullOrWhiteSpace($valor)) { return $PorDefecto }
    return $valor.Trim()
}

function Generar-SecretKey {
    # 48 bytes al azar, en base64 sin caracteres que compliquen un .env
    # (ni + ni / ni =). Mismo largo que sugiere backend/.env.example con
    # `secrets.token_urlsafe(48)`, pero sin depender de tener Python en el
    # PATH en este punto del instalador.
    # RandomNumberGenerator::Fill es de .NET moderno y no existe en .NET
    # Framework, que es lo que trae Windows PowerShell 5.1 (la que corre acá).
    # RNGCryptoServiceProvider sí está disponible en las dos versiones.
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [Convert]::ToBase64String($bytes) -replace '\+', '-' -replace '/', '_' -replace '=', ''
}

if (-not (Test-Path $CarpetaBackend)) {
    throw "No existe la carpeta de backend: $CarpetaBackend"
}

$rutaEnv = Join-Path $CarpetaBackend ".env"

if (Test-Path $rutaEnv) {
    if ($NoInteractivo) {
        Write-Host "Ya existe $rutaEnv — no se toca (modo no interactivo)." -ForegroundColor Yellow
        exit 0
    }
    $resp = Read-Host "Ya existe $rutaEnv. Sobreescribirlo cierra las sesiones abiertas. ¿Continuar? (s/N)"
    if ($resp -notmatch '^[sS]') {
        Write-Host "Cancelado. El .env existente no se tocó."
        exit 0
    }
}

Write-Host ""
Write-Host "=== Configuración inicial del Sistema de Inventario y POS ===" -ForegroundColor Cyan
Write-Host "Esto sólo se pide una vez por instalación." -ForegroundColor DarkGray
Write-Host ""

if (-not $ZonaHoraria) {
    Write-Host "Zona horaria del LOCAL (no del servidor, si son distintos)." -ForegroundColor DarkGray
    Write-Host "Define dónde empieza y termina 'el día' para los arqueos y reportes." -ForegroundColor DarkGray
    $ZonaHoraria = Pedir "Zona horaria (formato IANA)" "America/Argentina/Buenos_Aires"
}

if (-not $DireccionPublica) {
    Write-Host ""
    Write-Host "Dirección por la que el CELULAR del cliente llega a este servidor" -ForegroundColor DarkGray
    Write-Host "para pagar con QR. Nunca 'localhost': el celular no es esta PC." -ForegroundColor DarkGray
    Write-Host "Ejemplos: http://192.168.1.50  |  https://pos.tudominio.com" -ForegroundColor DarkGray
    $DireccionPublica = Pedir "Dirección pública del servidor" ""
    while (-not $NoInteractivo -and ($DireccionPublica -eq "" -or $DireccionPublica -match "localhost|127\.0\.0\.1")) {
        Write-Host "No puede quedar vacía ni apuntar a localhost (ENTORNO=produccion lo rechaza al arrancar)." -ForegroundColor Red
        $DireccionPublica = Pedir "Dirección pública del servidor" ""
    }
}

if (-not $CarpetaRespaldoExterno) {
    Write-Host ""
    Write-Host "Carpeta para la SEGUNDA copia de cada respaldo, fuera de este disco" -ForegroundColor DarkGray
    Write-Host "(OneDrive, Google Drive, o un pendrive que quede siempre puesto)." -ForegroundColor DarkGray
    Write-Host "Vacío = sólo copias locales, que no sirven si este disco se rompe." -ForegroundColor DarkGray
    $CarpetaRespaldoExterno = Pedir "Carpeta de respaldo externo (opcional)" ""
}

if (-not $NoInteractivo -and -not $MercadoPagoToken) {
    Write-Host ""
    Write-Host "Token de Mercado Pago productivo (empieza con APP_USR-)." -ForegroundColor DarkGray
    Write-Host "Vacío = el cobro por QR queda deshabilitado hasta cargarlo después." -ForegroundColor DarkGray
    $MercadoPagoToken = Pedir "MERCADOPAGO_ACCESS_TOKEN (opcional)" ""
}

$secretKey = Generar-SecretKey
$corsOrigins = "[`"$DireccionPublica`"]"
$frontendDist = (Join-Path (Split-Path -Parent $CarpetaBackend) "frontend\dist") -replace '\\', '/'

$contenido = @"
# Generado por installer\scripts\generar-env.ps1 — no se sube al repositorio.

SECRET_KEY=$secretKey
DATABASE_URL=sqlite:///./applify.db
MERCADOPAGO_ACCESS_TOKEN=$MercadoPagoToken
FRONTEND_URL=$DireccionPublica
RESPALDO_EXTERNO=$CarpetaRespaldoExterno
CORS_ORIGINS=$corsOrigins
FRONTEND_DIST=$frontendDist
PROXIES_CONFIABLES=$ProxiesConfiables
LIMITE_PETICIONES_POR_MINUTO=300
ZONA_HORARIA=$ZonaHoraria
ENTORNO=produccion
"@

Set-Content -Path $rutaEnv -Value $contenido -Encoding UTF8

Write-Host ""
Write-Host "Listo: $rutaEnv" -ForegroundColor Green
Write-Host "Revisalo antes de arrancar el servicio: en especial CORS_ORIGINS y FRONTEND_URL" -ForegroundColor DarkGray
Write-Host "tienen que ser la dirección real por la que entra el celular, no localhost." -ForegroundColor DarkGray
