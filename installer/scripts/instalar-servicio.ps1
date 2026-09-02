<#
    .SINOPSIS
    Registra el backend como servicio de Windows con NSSM: arranca solo al
    prender la máquina y se reinicia solo si el proceso se cae. Sin esto, un
    POS que hay que arrancar a mano se apaga el día que el dueño reinicia la PC
    (o corta la luz, o Windows actualiza y reinicia de madrugada).

    .DESCRIPCION
    Requiere permisos de administrador (crear un servicio los pide). Usa
    Python EMBEBIDO, no el del sistema: así la instalación no depende de que
    el comercio tenga Python instalado ni de qué versión.

    IMPORTANTE — AppDirectory: el backend resuelve rutas relativas (la base
    SQLite por defecto, backend/logs, backend/respaldos) contra el directorio
    de trabajo del proceso, no contra la ubicación del script. Por eso el
    servicio tiene que arrancar con AppDirectory = la carpeta backend/, igual
    que en desarrollo se corre `uvicorn app.main:app` parado ahí adentro.
    Instalar el servicio con el AppDirectory mal puesto crea una base nueva
    vacía la primera vez que arranca, en silencio.

    .PARAMETRO NombrePython
    Ejecutable de Python a usar. Por defecto el embebido que trae el
    instalador al lado de este script (vendor\python-embed\python.exe).

    .PARAMETRO Puerto
    Puerto donde escucha uvicorn. 80 sirve el POS sin escribir el puerto en
    la URL desde el celular, pero requiere que nada más lo esté usando y que
    el firewall lo tenga abierto (ver §4 de PARA-PRODUCCION.md: la red del
    local es un paso aparte, no algo que resuelva este script).
#>
[CmdletBinding()]
param(
    [string]$NombreServicio = "SistemaInventariosPOS",
    [string]$CarpetaInstalacion = (Split-Path -Parent $PSScriptRoot),
    [string]$NombrePython,
    [int]$Puerto = 8000,
    [string]$RutaNssm
)

$ErrorActionPreference = "Stop"

$actual = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $actual.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Este script necesita PowerShell como Administrador (crear un servicio de Windows lo requiere)."
}

if (-not $RutaNssm) { $RutaNssm = Join-Path $CarpetaInstalacion "vendor\nssm.exe" }
if (-not (Test-Path $RutaNssm)) {
    throw "No se encontró nssm.exe en $RutaNssm. Descargalo de https://nssm.cc/ y colocalo ahí " +
          "(no se distribuye en el repositorio: es un binario de terceros)."
}

$carpetaBackend = Join-Path $CarpetaInstalacion "backend"
if (-not (Test-Path (Join-Path $carpetaBackend ".env"))) {
    throw "Falta $carpetaBackend\.env — corré generar-env.ps1 antes de instalar el servicio."
}

if (-not $NombrePython) { $NombrePython = Join-Path $CarpetaInstalacion "vendor\python-embed\python.exe" }
if (-not (Test-Path $NombrePython)) {
    throw "No se encontró Python en $NombrePython. Preparar vendor\python-embed\ es un paso del " +
          "empaquetado (ver installer\README.md), no de este script."
}

$carpetaLogs = Join-Path $carpetaBackend "logs"
New-Item -ItemType Directory -Force -Path $carpetaLogs | Out-Null

$existente = & $RutaNssm status $NombreServicio 2>$null
if ($LASTEXITCODE -eq 0 -and $existente) {
    Write-Host "El servicio '$NombreServicio' ya existe (estado: $existente). Lo reconfiguro en vez de duplicarlo." -ForegroundColor Yellow
    & $RutaNssm stop $NombreServicio 2>$null | Out-Null
} else {
    & $RutaNssm install $NombreServicio $NombrePython
}

# Argumentos del proceso: el mismo comando que en desarrollo, con --host
# 0.0.0.0 para que conteste en toda la red del local y no sólo en esta PC.
& $RutaNssm set $NombreServicio AppParameters "-m uvicorn app.main:app --host 0.0.0.0 --port $Puerto"
& $RutaNssm set $NombreServicio AppDirectory $carpetaBackend
& $RutaNssm set $NombreServicio DisplayName "Sistema de Inventario y POS"
& $RutaNssm set $NombreServicio Description "Backend del POS. Detenerlo apaga la caja de todo el local."
& $RutaNssm set $NombreServicio Start SERVICE_AUTO_START

# Si el proceso se cae, que NSSM lo reinicie solo — pero no en bucle rápido
# si el problema es persistente (una migración pendiente, un .env roto):
# space entre reintentos y un techo, para que quede evidencia en logs\ en vez
# de un service que reinicia mil veces por segundo y ahoga el disco.
& $RutaNssm set $NombreServicio AppExit Default Restart
& $RutaNssm set $NombreServicio AppRestartDelay 3000
& $RutaNssm set $NombreServicio AppThrottle 5000

# stdout/stderr del proceso, aparte del logging propio de la app (que ya
# escribe en backend\logs\backend.log): esto captura además lo que pasa antes
# de que el logging se inicialice, como un traceback de arranque.
& $RutaNssm set $NombreServicio AppStdout (Join-Path $carpetaLogs "servicio.out.log")
& $RutaNssm set $NombreServicio AppStderr (Join-Path $carpetaLogs "servicio.err.log")
& $RutaNssm set $NombreServicio AppRotateFiles 1
& $RutaNssm set $NombreServicio AppRotateBytes 2000000

& $RutaNssm start $NombreServicio

Write-Host ""
Write-Host "Servicio '$NombreServicio' instalado y arrancado en el puerto $Puerto." -ForegroundColor Green
Write-Host "Verificar: nssm status $NombreServicio" -ForegroundColor DarkGray
