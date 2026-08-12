# Sistema de Inventario y Punto de Venta

POS e inventario para comercios chicos. Backend FastAPI + SQLite, frontend React + Vite.
El README explica el producto; este archivo es para trabajar sobre el código.

## Cómo levantarlo

```bash
# Backend (desde backend/)
venv\Scripts\activate
alembic upgrade head        # después de traer cambios: puede haber migraciones
uvicorn app.main:app --reload

# Frontend (desde frontend/)
pnpm dev                    # pnpm, no npm: hay lockfile de pnpm
```

## Tests

```bash
cd backend  && venv\Scripts\activate && pytest        # ~245, tardan ~2:30
cd frontend && pnpm test                              # vitest
```

Los de backend corren contra una SQLite temporal que se crea y borra sola
(`tests/conftest.py`); nunca tocan `applify.db`. Los de frontend usan jsdom con
`fake-indexeddb`, y hay polyfills necesarios en `src/tests/setup.ts` —
`localStorage` entre ellos, porque el de Node pisa al de jsdom.

`pnpm lint` corre pero hoy reporta ~140 hallazgos viejos (sobre todo `any` en
`api.ts` y `exportExcel.ts`). Estuvo roto un tiempo, así que nunca se limpiaron:
no los tomes como algo que rompiste vos.

## Convenciones

- **Todo en español**: nombres, comentarios, docstrings, mensajes de error y
  commits. Los commits usan `feat:` / `fix:` / `test:` / `docs:` y describen el
  efecto para el comercio, no el cambio mecánico.
- **Los comentarios explican el porqué**, no el qué. Muchos documentan un bug
  concreto que se corrigió; si tocás ese código, el comentario es contexto
  valioso, no relleno.
- **Nunca commitear** `.env`, `*.db`, `backend/respaldos/`, `backend/logs/` ni
  certificados. Ya están en `.gitignore`.

## Reglas del dominio que no se negocian

Estas ya costaron un bug o un agujero de seguridad. Si un cambio las toca,
tiene que ser a propósito.

- **El precio y el total los decide el servidor**, siempre, con el catálogo de
  la base. Lo que manda el cliente en `precio_unitario` es informativo.
- **Un cobro por QR se confirma contra Mercado Pago desde el backend**, con el
  total que calculó el propio servidor, y su `pago_referencia` es único: un
  pago no puede respaldar dos ventas.
- **El POS tiene que poder vender sin red.** Las ventas se guardan en IndexedDB
  y se sincronizan solas. Cualquier cosa que exija servidor para cobrar rompe
  la promesa central del producto.
- **Las ventas no se borran.** Anular deja el registro y suma una devolución
  que lo referencia. Las bajas de usuario también son lógicas (`estado`).
- **Los movimientos de stock se auditan**: quién, cuándo y por qué.
- **El rol y el estado del usuario se leen de la base en cada request**, no del
  token, para que un cambio de permisos o una baja corten las sesiones abiertas.

## Cosas que sorprenden

- `config.py` valida al arrancar y **aborta en producción** si falta
  `SECRET_KEY`, si está la clave vieja que quedó en el historial de git, o si
  `CORS_ORIGINS` es `*`.
- **`with_for_update()` no hace nada en SQLite**: compila a un SELECT pelado.
  Por eso el descuento de stock en `ventas.py` se hace con un UPDATE relativo
  (`stock_actual - :n`) y no leyendo y restando en Python.
- Las fechas se guardan en **UTC** y se muestran en hora local. `reportes.py`
  tiene los helpers de conversión; un reporte que arma rangos a mano va a dar
  mal en el borde del día.
- El freno al login cuenta dos cosas distintas: intentos por cuenta, e
  **cuántas cuentas distintas** se probaron desde una IP. Lo segundo es contra
  el barrido; contar intentos a secas dejaba sin entrar a todo un local detrás
  de un router.
- `frontend/src/Admin.tsx` tiene 3000+ líneas y `App.tsx` 1600. Al agregar algo
  grande, conviene sacarlo a un módulo aparte en vez de engordarlos más.

## Dónde está cada cosa

```
backend/app/
  routers/       un archivo por área; cada endpoint declara su rol requerido
  models.py      SQLAlchemy. Un cambio acá necesita migración de alembic
  schemas.py     Pydantic (entrada/salida de la API)
  auth.py        hash de PIN, tokens y freno de fuerza bruta
  respaldos.py   copias de la base (locales y a la carpeta externa del .env)
frontend/src/
  App.tsx        el POS (venta, teclado, offline)
  Admin.tsx      backoffice
  db.ts          IndexedDB: catálogo local y cola de ventas offline
  api.ts         cliente HTTP
  sincronizacion.ts  qué hacer con una venta que el servidor rechazó
```
