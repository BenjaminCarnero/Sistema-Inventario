<#
    .SINOPSIS
    Detiene y quita el servicio de Windows. Lo llama el desinstalador de
    Inno Setup antes de borrar los archivos del programa.

    NO toca backend\applify.db, backend\respaldos\, backend\logs\ ni
    backend\.env — de eso se encarga (o mejor dicho, deliberadamente NO se
    encarga) el propio installer\setup.iss: esos archivos nunca están
    declarados en [Files], así que el desinstalador de Inno Setup no los
    conoce y no los borra. Este script tampoco los toca por las dudas.
#>
[CmdletBinding()]
param(
    [string]$NombreServicio = "SistemaInventariosPOS",
    [string]$RutaNssm
)

$ErrorActionPreference = "Continue"  # que un servicio ya ausente no aborte la desinstalación

if (-not $RutaNssm) { $RutaNssm = Join-Path (Split-Path -Parent $PSScriptRoot) "vendor\nssm.exe" }

if (-not (Test-Path $RutaNssm)) {
    Write-Host "No se encontró nssm.exe — si el servicio quedó instalado, quitalo a mano con:" -ForegroundColor Yellow
    Write-Host "  sc.exe delete $NombreServicio" -ForegroundColor Yellow
    exit 0
}

$estado = & $RutaNssm status $NombreServicio 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "El servicio '$NombreServicio' no existe. Nada que desinstalar."
    exit 0
}

Write-Host "Deteniendo '$NombreServicio'..."
& $RutaNssm stop $NombreServicio | Out-Null
Start-Sleep -Seconds 2
& $RutaNssm remove $NombreServicio confirm | Out-Null

Write-Host "Servicio quitado. La base, los respaldos y los logs quedaron intactos en su carpeta." -ForegroundColor Green
