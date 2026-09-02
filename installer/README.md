# Instalador de Windows

Cubre la parte de [PARA-PRODUCCION.md](../PARA-PRODUCCION.md) §1 que es 100%
scripting: generar el `.env`, instalar el servicio de Windows y empaquetar
todo con Inno Setup. El primer administrador **no** se crea acá — lo resuelve
el asistente de primer arranque que aparece en el propio POS
([`App.tsx`](../frontend/src/App.tsx) + `GET /auth/estado-inicial`).

## Qué está probado y qué no

Esta máquina de desarrollo no tiene Inno Setup ni NSSM instalados, así que lo
que sigue **no se compiló ni se corrió como instalador real**. Lo que sí se
verificó, sin instalar nada en el sistema:

| Archivo | Verificación real hecha |
|---|---|
| `scripts/generar-env.ps1` | Parseo sin errores, corrida en modo `-NoInteractivo` contra una carpeta de prueba, y el `.env` que generó **pasó la validación estricta** de `ENTORNO=produccion` en `backend/app/config.py` sin abortar (se probó importando `app.config` con ese `.env`, después restaurado el original). |
| `scripts/instalar-servicio.ps1` | Parseo sin errores. Se corrió sin privilegios de administrador y frenó con el mensaje correcto en vez de fallar feo — es lo único que se puede probar sin NSSM ni permisos elevados. |
| `scripts/desinstalar-servicio.ps1` | Parseo sin errores. No se ejecutó de punta a punta (necesita un servicio real instalado). |
| `setup.iss` | Sólo leído contra la documentación de Inno Setup. Nunca se compiló: no hay `iscc` en esta máquina. |

De hecho, escribir estos scripts sin poder correrlos ya encontró y corrigió dos
bugs reales al probarlos:

1. `generar-env.ps1` usaba `RandomNumberGenerator::Fill`, que es de .NET
   moderno y no existe en .NET Framework — que es lo que trae **Windows
   PowerShell 5.1**, la que de verdad va a correr esto en un comercio. Se
   cambió a `RNGCryptoServiceProvider`, disponible en ambos.
2. Los tres `.ps1` se habían guardado sin BOM. Windows PowerShell 5.1, sin BOM,
   adivina la codificación por el codepage del sistema en vez de asumir UTF-8,
   así que los acentos (á, é, í, ó, —) se corrompían y rompían las cadenas de
   texto a la mitad. Se reescribieron con BOM UTF-8.

Sin estas dos correcciones, el script habría fallado en la primera instalación
real, en la máquina de un comercio, con un error de .NET que no dice nada
sobre la causa.

## Prerrequisitos para terminar esto

1. **Compilar el frontend primero**: `cd frontend && pnpm build`. El
   instalador empaqueta `frontend/dist`, no lo genera.
2. **Preparar `vendor/`** (no se distribuye en el repositorio: son binarios de
   terceros; el `.gitignore` de este proyecto ya evita que se suban por
   accidente si los descargás acá adentro):
   - `vendor/nssm.exe` — bajarlo de <https://nssm.cc/download> (versión
     2.24). Usar el `.exe` de la carpeta `win64/`.
   - `vendor/python-embed/` — el "Windows embeddable package" de
     <https://www.python.org/downloads/windows/> (3.11.x, misma versión que
     usa `backend/venv`), descomprimido ahí adentro. Un embebido de fábrica
     **no trae pip**: hay que bootstrapearlo una vez con
     [`get-pip.py`](https://bootstrap.pypa.io/get-pip.py) y, en el archivo
     `python311._pth` que trae el zip, descomentar la línea `#import site`
     (si no, ni pip ni los paquetes instalados se importan).
3. **Instalar Inno Setup 6** (gratis): <https://jrsoftware.org/isinfo.php>.
4. Compilar: `iscc installer\setup.iss` desde la carpeta `installer/`. El
   `.exe` queda en `installer/dist/`.
5. **Probar en una VM de Windows limpia**, no en la máquina de desarrollo:
   instalar, verificar que el servicio arranca solo, reiniciar la VM y
   confirmar que sigue andando, y recién ahí abrir el POS y pasar por el
   asistente de primer arranque.

## Por qué no lo hice yo en esta sesión

Descargar `nssm.exe` y el embebible de Python son descargas de binarios de
terceros, e instalar el servicio de verdad modifica el sistema (crea un
servicio de Windows) — ninguna de las dos cosas las hago sin que las pidas en
el momento. Los scripts y el `.iss` están listos para que alguien con esas
herramientas a mano los compile y los pruebe en una VM.

## Decisiones que quedaron tomadas (y por qué)

- **Todo vive bajo `{app}`**, incluida la base SQLite y el `.env` — no se usa
  `ProgramData`. El servicio corre como `LocalSystem` (lo que instala NSSM por
  defecto), que puede escribir en `Program Files` sin la virtualización de UAC
  que afecta a procesos de usuario normal. Simplifica el instalador a costa de
  no separar "programa" de "datos" — aceptable para una v1 de un solo
  comercio por instalación; reconsiderar si algún día hay que dar permisos de
  Windows más finos por usuario.
- **El puerto por defecto es 8000**, no el 80 "de verdad sin escribir puerto"
  ni el 8001 de desarrollo. 80 puede estar tomado por IIS/Skype/otro POS; 8001
  es el de desarrollo y mezclarlos confunde al debuggear. Es un parámetro de
  `instalar-servicio.ps1`, se cambia fácil.
- **`generar-env.ps1` no pide el nombre del comercio.** Se pidió explícitamente
  en `PARA-PRODUCCION.md`, pero ese dato ya lo pide el asistente web de primer
  arranque y queda guardado en la base (`negocio_nombre`, vía
  `PUT /configuracion`) — pedirlo dos veces en dos lugares distintos es peor
  UX, no mejor. La zona horaria sí se pide acá porque es una variable de
  entorno del proceso: no se puede cambiar desde una pantalla sin reiniciar
  el servicio, así que no puede vivir en el asistente web.

## Lo que sigue faltando de §1 después de esto

- Firma de código (🟢, cuesta dinero — explícitamente puede esperar).
- Instalación fake→real: nadie corrió este instalador todavía en una VM.
  Hasta que eso pase, tratarlo como un borrador serio, no como probado.
