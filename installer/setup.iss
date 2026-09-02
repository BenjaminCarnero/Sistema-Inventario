; Instalador del Sistema de Inventario y Punto de Venta.
;
; NO ESTA COMPILADO NI PROBADO TODAVIA: se escribió sin tener Inno Setup
; instalado en la máquina de desarrollo. Antes de confiar en él:
;   1. Instalar Inno Setup 6 (gratis): https://jrsoftware.org/isinfo.php
;   2. Preparar installer\vendor\ (ver installer\README.md — NO viene armado)
;   3. Compilar: "iscc installer\setup.iss" y probar en una VM limpia de Windows
;
; Qué hace, en orden:
;   1. Copia backend/ (código, no la base ni el .env) y frontend/dist/ ya
;      compilado, más un Python embebido y nssm.exe.
;   2. Corre generar-env.ps1 (interactivo): pide zona horaria y dirección
;      pública, genera una SECRET_KEY propia, escribe backend\.env.
;   3. Instala las dependencias de Python con el embebido (necesita que
;      vendor\python-embed ya tenga pip — ver README) y migra la base
;      (alembic upgrade head).
;   4. Instala y arranca el servicio de Windows con NSSM.
;
; El primer administrador NO se crea acá: se crea la primera vez que se abre
; el POS en el navegador, con el asistente de primer arranque
; (frontend/src/App.tsx + GET /auth/estado-inicial). Este instalador sólo
; deja el servidor prendido y esperando esa primera visita.

#define MyAppName "Sistema de Inventario y POS"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Tu empresa"
; Servicio de Windows: tiene que coincidir con instalar-servicio.ps1
#define MyServiceName "SistemaInventariosPOS"

[Setup]
AppId={{B6E1A6C4-6E7B-4B2E-9C2E-APPLIFYPOS001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SistemaInventariosPOS
DefaultGroupName={#MyAppName}
; Crear el servicio de Windows requiere administrador.
PrivilegesRequired=admin
OutputDir=dist
OutputBaseFilename=SistemaInventariosPOS-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
; SmartScreen va a avisar igual hasta que haya firma de código (§1, ítem
; verde: "puede esperar"). No es un error del instalador.
WizardStyle=modern
; No hay un .ico propio en el repositorio todavía (sólo íconos web PWA en
; frontend/public/). Agregar uno y apuntar UninstallDisplayIcon acá es
; cosmético, no bloqueante.

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
; Código del backend. NUNCA declarar acá .env, applify.db*, logs\* ni
; respaldos\*: son datos de la instalación, no del paquete, y si Inno Setup
; los llega a "conocer" el desinstalador los puede borrar.
Source: "..\backend\app\*"; DestDir: "{app}\backend\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\backend\alembic\*"; DestDir: "{app}\backend\alembic"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\backend\alembic.ini"; DestDir: "{app}\backend"; Flags: ignoreversion
Source: "..\backend\requirements.txt"; DestDir: "{app}\backend"; Flags: ignoreversion
Source: "..\backend\seed_admin.py"; DestDir: "{app}\backend"; Flags: ignoreversion
Source: "..\backend\restaurar_respaldo.py"; DestDir: "{app}\backend"; Flags: ignoreversion

; Frontend ya compilado. El packager tiene que correr "pnpm build" en
; frontend/ ANTES de compilar este instalador — no lo hace este script.
Source: "..\frontend\dist\*"; DestDir: "{app}\frontend\dist"; Flags: ignoreversion recursesubdirs createallsubdirs

; Python embebido y NSSM: binarios de terceros, no viven en el repositorio.
; Ver installer\README.md para cómo prepararlos antes de compilar.
Source: "vendor\python-embed\*"; DestDir: "{app}\vendor\python-embed"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\nssm.exe"; DestDir: "{app}\vendor"; Flags: ignoreversion

Source: "scripts\generar-env.ps1"; DestDir: "{app}\installer\scripts"; Flags: ignoreversion
Source: "scripts\instalar-servicio.ps1"; DestDir: "{app}\installer\scripts"; Flags: ignoreversion
Source: "scripts\desinstalar-servicio.ps1"; DestDir: "{app}\installer\scripts"; Flags: ignoreversion

[Run]
; 1) Configuración inicial — interactivo, se ve la consola a propósito.
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\scripts\generar-env.ps1"" -CarpetaBackend ""{app}\backend"""; \
    StatusMsg: "Configurando zona horaria y dirección del servidor..."; \
    Flags: waituntilterminated

; 2) Dependencias de Python. Requiere que vendor\python-embed\ ya tenga pip
; (ver README): un embebido "de fábrica" no lo trae.
Filename: "{app}\vendor\python-embed\python.exe"; \
    Parameters: "-m pip install -r requirements.txt --no-warn-script-location"; \
    WorkingDir: "{app}\backend"; \
    StatusMsg: "Instalando dependencias..."; \
    Flags: waituntilterminated

; 3) Migrar la base a la última versión. En una instalación nueva la crea
; desde cero; en una actualización, la deja al día (ver §2 de
; PARA-PRODUCCION.md: esto también es la mitad del camino para el botón de
; actualización remota, que todavía no existe).
Filename: "{app}\vendor\python-embed\python.exe"; \
    Parameters: "-m alembic upgrade head"; \
    WorkingDir: "{app}\backend"; \
    StatusMsg: "Preparando la base de datos..."; \
    Flags: waituntilterminated

; 4) Servicio de Windows: arranca solo, se reinicia solo si se cae.
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\scripts\instalar-servicio.ps1"" -CarpetaInstalacion ""{app}"""; \
    StatusMsg: "Instalando el servicio de Windows..."; \
    Flags: waituntilterminated

Filename: "http://localhost:8000"; Description: "Abrir el POS ahora"; Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\scripts\desinstalar-servicio.ps1"""; \
    RunOnceId: "QuitarServicioPOS"; \
    Flags: waituntilterminated

[UninstallDelete]
; Sólo lo que instaló este paquete. NO incluir backend\applify.db*,
; backend\logs ni backend\respaldos: al no estar en [Files] tampoco están acá,
; y el desinstalador de Inno Setup no borra lo que no declaró — es
; justamente lo que hace que "desinstalar no borre la base" sea cierto sin
; tener que acordarse de nada en el momento.
Type: filesandordirs; Name: "{app}\backend\app"
Type: filesandordirs; Name: "{app}\backend\alembic"
Type: filesandordirs; Name: "{app}\backend\__pycache__"
Type: filesandordirs; Name: "{app}\frontend"
Type: filesandordirs; Name: "{app}\vendor"
Type: filesandordirs; Name: "{app}\installer"
