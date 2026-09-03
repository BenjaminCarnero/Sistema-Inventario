<#
    .SINOPSIS
    Actualiza una instalación existente: baja la versión nueva (o usa un .zip
    ya descargado), hace un respaldo ANTES de tocar nada, reemplaza el código,
    migra la base y reinicia el servicio. Si la migración falla, vuelve todo
    atrás — código y base — a la versión anterior.

    .DESCRIPCION
    "Esto es lo más importante de todo el documento y lo más fácil de
    postergar" (PARA-PRODUCCION.md §2). Sin esto, un bug en el arqueo de un
    comercio remoto sólo se arregla yendo o pidiendo escritorio remoto.

    Qué NUNCA toca, pase lo que pase: backend\.env, backend\applify.db*,
    backend\logs\ y backend\respaldos\. Sólo se reemplaza código (app/,
    alembic/, alembic.ini, requirements.txt, seed_admin.py,
    restaurar_respaldo.py, frontend/dist, VERSION).

    .PARAMETRO ArchivoZip
    Ruta a un .zip de release ya descargado (mismo formato que publica
    release.yml). Si no se pasa, lo baja de GitHub Releases. Pensado también
    para poder probar el mecanismo entero sin depender de la red ni de que
    exista un release publicado.

    .PARAMETRO OmitirServicio
    No para ni arranca el servicio de Windows: para instalaciones que
    todavía corren el backend a mano, o para probar el mecanismo de
    actualización sin tener NSSM instalado.

    .PARAMETRO Forzar
    Aplica el paquete aunque su VERSION no sea más nueva que la instalada.
    Sirve para reinstalar la misma versión (por ejemplo, si una actualización
    anterior dejó archivos a medio copiar).
#>
[CmdletBinding()]
param(
    [string]$CarpetaInstalacion = (Split-Path -Parent $PSScriptRoot),
    [string]$ArchivoZip,
    [string]$Repositorio = "BenjaminCarnero/Sistema-Inventario",
    [string]$NombreServicio = "SistemaInventariosPOS",
    [string]$RutaNssm,
    [string]$RutaPython,
    [switch]$OmitirServicio,
    [switch]$Forzar,
    [switch]$SinConfirmar
)

$ErrorActionPreference = "Stop"

function Version-A-Tupla([string]$v) {
    ($v -replace '^[vV]', '') -split '\.' | ForEach-Object { [int]($_ -replace '\D', '') }
}

function Version-Es-Mayor([string]$nueva, [string]$actual) {
    $a = @(Version-A-Tupla $nueva)
    $b = @(Version-A-Tupla $actual)
    for ($i = 0; $i -lt [Math]::Max($a.Count, $b.Count); $i++) {
        $x = if ($i -lt $a.Count) { $a[$i] } else { 0 }
        $y = if ($i -lt $b.Count) { $b[$i] } else { 0 }
        if ($x -ne $y) { return $x -gt $y }
    }
    return $false
}

if (-not $OmitirServicio) {
    $actual = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $actual.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Este script necesita PowerShell como Administrador (parar/arrancar el servicio lo requiere). " +
              "Usá -OmitirServicio si el backend corre a mano, sin servicio de Windows."
    }
}

$carpetaBackend = Join-Path $CarpetaInstalacion "backend"
$carpetaFrontend = Join-Path $CarpetaInstalacion "frontend"
$archivoVersion = Join-Path $CarpetaInstalacion "VERSION"

if (-not (Test-Path $carpetaBackend)) { throw "No existe $carpetaBackend — ¿CarpetaInstalacion está bien?" }

$versionActual = if (Test-Path $archivoVersion) { (Get-Content $archivoVersion -Raw).Trim() } else { "0.0.0" }
Write-Host "Versión instalada: $versionActual" -ForegroundColor Cyan

# --- 1) Conseguir el paquete nuevo -------------------------------------------
$zipDescargado = $null
if (-not $ArchivoZip) {
    Write-Host "Buscando la última versión en GitHub ($Repositorio)..."
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repositorio/releases/latest" `
        -Headers @{ Accept = "application/vnd.github+json" }

    $versionNueva = $release.tag_name -replace '^[vV]', ''
    $asset = $release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "El release '$($release.tag_name)' no tiene ningún .zip adjunto." }

    if (-not $Forzar -and -not (Version-Es-Mayor $versionNueva $versionActual)) {
        Write-Host "Ya estás en la última versión ($versionActual). Nada que hacer." -ForegroundColor Green
        exit 0
    }

    $zipDescargado = Join-Path $env:TEMP $asset.name
    Write-Host "Descargando $($asset.name)..."
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipDescargado
    $ArchivoZip = $zipDescargado
}

if (-not (Test-Path $ArchivoZip)) { throw "No existe el archivo: $ArchivoZip" }

# --- 2) Extraer a una carpeta temporal y leer su VERSION ---------------------
$carpetaExtraida = Join-Path $env:TEMP ("actualizacion_" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
Expand-Archive -Path $ArchivoZip -DestinationPath $carpetaExtraida -Force

$versionPaquete = Join-Path $carpetaExtraida "VERSION"
if (-not (Test-Path $versionPaquete)) { throw "El paquete no tiene un archivo VERSION en la raíz: no se puede confiar en él." }
$versionNuevaPaquete = (Get-Content $versionPaquete -Raw).Trim()

if (-not $Forzar -and -not (Version-Es-Mayor $versionNuevaPaquete $versionActual)) {
    Write-Host "El paquete ($versionNuevaPaquete) no es más nuevo que lo instalado ($versionActual). Usá -Forzar si igual querés aplicarlo." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $carpetaExtraida
    exit 0
}

Write-Host ""
Write-Host "Se va a actualizar $versionActual -> $versionNuevaPaquete" -ForegroundColor Cyan
if (-not $SinConfirmar) {
    if ((Read-Host "Escribí 'actualizar' para confirmar") -ne "actualizar") {
        Write-Host "Cancelado. No se tocó nada."
        Remove-Item -Recurse -Force $carpetaExtraida
        exit 0
    }
}

# --- 3) Rutas de python/nssm, igual que instalar-servicio.ps1 ---------------
if (-not $RutaPython) { $RutaPython = Join-Path $CarpetaInstalacion "vendor\python-embed\python.exe" }
if (-not (Test-Path $RutaPython)) { throw "No se encontró Python en $RutaPython." }
if (-not $OmitirServicio) {
    if (-not $RutaNssm) { $RutaNssm = Join-Path $CarpetaInstalacion "vendor\nssm.exe" }
    if (-not (Test-Path $RutaNssm)) { throw "No se encontró nssm.exe en $RutaNssm." }
}

# --- 4) Respaldo ANTES de tocar nada -----------------------------------------
# Si esto falla, se corta acá: sin respaldo no hay vuelta atrás posible, así
# que no tiene sentido seguir.
Write-Host "Haciendo un respaldo antes de actualizar..."
Push-Location $carpetaBackend
try {
    $nombreRespaldo = & $RutaPython -c "from app import respaldos; r = respaldos.crear('antes_de_actualizar'); print(r.name if r else '')"
} finally {
    Pop-Location
}
if (-not $nombreRespaldo) {
    Remove-Item -Recurse -Force $carpetaExtraida
    throw "No se pudo hacer el respaldo previo. Se cancela la actualización sin tocar nada."
}
Write-Host "Respaldo hecho: $nombreRespaldo" -ForegroundColor Green

# --- 5) Parar el servicio -----------------------------------------------------
if (-not $OmitirServicio) {
    Write-Host "Deteniendo el servicio..."
    & $RutaNssm stop $NombreServicio | Out-Null
    Start-Sleep -Seconds 2
}

# --- 6) Guardar el código actual por si hay que volver atrás -----------------
$carpetaRollback = Join-Path $CarpetaInstalacion "_rollback_temp"
if (Test-Path $carpetaRollback) { Remove-Item -Recurse -Force $carpetaRollback }
New-Item -ItemType Directory -Force -Path $carpetaRollback | Out-Null
Copy-Item (Join-Path $carpetaBackend "app") (Join-Path $carpetaRollback "app") -Recurse
Copy-Item (Join-Path $carpetaBackend "alembic") (Join-Path $carpetaRollback "alembic") -Recurse
Copy-Item (Join-Path $carpetaBackend "alembic.ini") (Join-Path $carpetaRollback "alembic.ini")
if (Test-Path (Join-Path $carpetaFrontend "dist")) {
    Copy-Item (Join-Path $carpetaFrontend "dist") (Join-Path $carpetaRollback "dist") -Recurse
}
if (Test-Path $archivoVersion) { Copy-Item $archivoVersion (Join-Path $carpetaRollback "VERSION") }

function Restaurar-CodigoAnterior {
    Remove-Item -Recurse -Force (Join-Path $carpetaBackend "app")
    Copy-Item (Join-Path $carpetaRollback "app") (Join-Path $carpetaBackend "app") -Recurse
    Remove-Item -Recurse -Force (Join-Path $carpetaBackend "alembic")
    Copy-Item (Join-Path $carpetaRollback "alembic") (Join-Path $carpetaBackend "alembic") -Recurse
    Copy-Item (Join-Path $carpetaRollback "alembic.ini") (Join-Path $carpetaBackend "alembic.ini") -Force
    if (Test-Path (Join-Path $carpetaRollback "dist")) {
        Remove-Item -Recurse -Force (Join-Path $carpetaFrontend "dist") -ErrorAction SilentlyContinue
        Copy-Item (Join-Path $carpetaRollback "dist") (Join-Path $carpetaFrontend "dist") -Recurse
    }
    if (Test-Path (Join-Path $carpetaRollback "VERSION")) {
        Copy-Item (Join-Path $carpetaRollback "VERSION") $archivoVersion -Force
    }
}

function Restaurar-BaseAnterior {
    # Mismo criterio que restaurar_respaldo.py: los -wal/-shm son de la base
    # que se está por reemplazar y dejarlos corrompe la que se restaura.
    $rutaBase = Join-Path $carpetaBackend "applify.db"
    $rutaRespaldo = Join-Path $carpetaBackend "respaldos\$nombreRespaldo"
    foreach ($sufijo in @("-wal", "-shm")) {
        $acompanante = "$rutaBase$sufijo"
        if (Test-Path $acompanante) { Remove-Item -Force $acompanante }
    }
    Copy-Item $rutaRespaldo $rutaBase -Force
}

# --- 7) Reemplazar el código --------------------------------------------------
try {
    Write-Host "Copiando el código nuevo..."
    foreach ($carpeta in @("app", "alembic")) {
        Remove-Item -Recurse -Force (Join-Path $carpetaBackend $carpeta)
        Copy-Item (Join-Path $carpetaExtraida $carpeta) (Join-Path $carpetaBackend $carpeta) -Recurse
    }
    foreach ($archivo in @("alembic.ini", "requirements.txt", "seed_admin.py", "restaurar_respaldo.py")) {
        $origen = Join-Path $carpetaExtraida $archivo
        if (Test-Path $origen) { Copy-Item $origen (Join-Path $carpetaBackend $archivo) -Force }
    }
    if (Test-Path (Join-Path $carpetaExtraida "dist")) {
        Remove-Item -Recurse -Force (Join-Path $carpetaFrontend "dist") -ErrorAction SilentlyContinue
        Copy-Item (Join-Path $carpetaExtraida "dist") (Join-Path $carpetaFrontend "dist") -Recurse
    }
    Copy-Item $versionPaquete $archivoVersion -Force

    Write-Host "Instalando dependencias..."
    & $RutaPython -m pip install -r (Join-Path $carpetaBackend "requirements.txt") --no-warn-script-location --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip install terminó con código $LASTEXITCODE" }

    Write-Host "Migrando la base..."
    Push-Location $carpetaBackend
    try {
        & $RutaPython -m alembic upgrade head
        $codigoMigracion = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($codigoMigracion -ne 0) { throw "alembic upgrade head terminó con código $codigoMigracion" }

    if (-not $OmitirServicio) {
        & $RutaNssm start $NombreServicio | Out-Null
    }

    Remove-Item -Recurse -Force $carpetaRollback
    Remove-Item -Recurse -Force $carpetaExtraida
    if ($zipDescargado) { Remove-Item -Force $zipDescargado -ErrorAction SilentlyContinue }

    Write-Host ""
    Write-Host "Actualizado a $versionNuevaPaquete." -ForegroundColor Green

} catch {
    Write-Host ""
    Write-Host "FALLÓ LA ACTUALIZACIÓN: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Volviendo a la versión anterior ($versionActual)..." -ForegroundColor Yellow

    Restaurar-CodigoAnterior
    Restaurar-BaseAnterior

    if (-not $OmitirServicio) {
        & $RutaNssm start $NombreServicio | Out-Null
    }

    Remove-Item -Recurse -Force $carpetaRollback -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $carpetaExtraida -ErrorAction SilentlyContinue

    Write-Host "Se volvió a $versionActual. El respaldo previo a intentar la actualización era: $nombreRespaldo" -ForegroundColor Yellow
    Write-Host "Revisá backend\logs antes de reintentar." -ForegroundColor Yellow
    exit 1
}
