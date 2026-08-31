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
- **El token identifica por id (`sub`) y lleva la versión de credencial
  (`cv`)**. Por nombre no: renombrar a un cajero y crear después otro usuario
  con el nombre viejo convertía su sesión abierta en una de administrador. La
  versión se incrementa al cambiar o reiniciar un PIN, y así ese cambio corta
  las sesiones al instante. El `nombre` que viaja en el token es sólo para
  mostrarlo en pantalla: no se lee para decidir nada.
- **El stock nunca se mueve sin dejar rastro.** `PUT /productos` no acepta
  `stock_actual`: se movía el inventario sin generar movimiento ni auditoría,
  que es justo como se tapa un faltante. Todo pasa por `/stock/movimientos`.
- **Los productos tampoco se borran**: `activo = False`. Las ventas, los
  movimientos y los pedidos los siguen referenciando.

## Cosas que sorprenden

- `config.py` valida al arrancar y **aborta en producción** si falta
  `SECRET_KEY`, si está la clave vieja que quedó en el historial de git, o si
  `CORS_ORIGINS` es `*`.
- **`with_for_update()` no hace nada en SQLite**: compila a un SELECT pelado.
  Por eso el stock se mueve con UPDATE relativos (`stock_actual - :n`) en
  `ventas.py`, `stock.py`, `devoluciones.py` y `pedidos.py`, y no leyendo y
  restando en Python. Las dos últimas arrastraron el patrón roto un tiempo:
  si tocás stock en un archivo nuevo, mirá cómo lo hace `ventas.py`.
- **El POS puede entrar sin servidor** (`frontend/src/sesionLocal.ts`): al
  iniciar sesión bien se guarda un PBKDF2 del PIN en el equipo, y sin red se
  valida contra eso. Esa sesión no tiene token, así que sirve para vender y no
  para el backoffice, y vence a los 30 días del último acceso real.
- **Una venta offline manda su propia hora** (`fecha_hora_local`) y el total que
  decía el ticket (`total_cobrado`). El servidor recalcula el total con su
  catálogo —eso no se negocia— y si no coincide lo deja en la auditoría.
- **La API tiene que devolver 404**. Cuando hay un `frontend/dist` al lado, el
  catch-all de `main.py` sirve el SPA; todo lo que empiece con un prefijo de
  `PREFIJOS_API` devuelve 404 JSON. Sin eso la API entera contestaba 200 con
  HTML. CI corre la suite dos veces, con y sin `dist`, justo por esto.
- Las fechas se guardan en **UTC** y se muestran en hora local. Los helpers
  están en `app/fechas.py` y hay que usarlos siempre: cuando vivían dentro de
  `reportes.py`, el historial de stock y la auditoría siguieron filtrando con
  fechas naive y traían mal el borde del día. Qué es "el día del local" lo
  define `ZONA_HORARIA` del `.env`; sin ella se usa el reloj del servidor, que
  sólo está bien si el servidor está en el mostrador.
- La base abre en **WAL** con `busy_timeout` de 10s (`database.py`), que es lo
  que permite que dos cajas cobren a la vez sin "database is locked". Deja
  archivos `-wal` y `-shm` al lado de la base: son normales, y hay que borrarlos
  al reemplazar la base a mano.
- Las **claves foráneas están activadas**. SQLite las ignora por defecto, así
  que hay código viejo que puede estar apoyándose en eso: si algo empieza a
  fallar con "FOREIGN KEY constraint failed", es que siempre estuvo mal.
- La política de largo del PIN vive en `app/auth.py:pin_minimo` porque la usan
  el router y `seed_admin.py`. Duplicada, el instalador dejaba crear el primer
  administrador con un PIN más débil del que exige la API.
- El freno al login cuenta dos cosas distintas: intentos por cuenta, e
  **cuántas cuentas distintas** se probaron desde una IP. Lo segundo es contra
  el barrido; contar intentos a secas dejaba sin entrar a todo un local detrás
  de un router.
- La IP sale de `app/red.py` y no de `request.client.host`. Detrás de un
  reverse proxy hay que poner `PROXIES_CONFIABLES=1` en el `.env`: si no, todas
  las cajas comparten IP y los dos frenos de arriba dejan de servir. Se cuenta
  desde la **derecha** de `X-Forwarded-For`, porque la izquierda la inventa el
  cliente.
- Hay un segundo freno, general y por IP (`LIMITE_PETICIONES_POR_MINUTO`), que
  vive en memoria. Los tests lo corren **apagado** desde `conftest.py`: todas
  las peticiones de la suite salen de la misma IP y se sumaban en un solo
  contador, así que los tests del final morían con 429 sin tener nada que ver.
- `frontend/src/Admin.tsx` tiene 3000+ líneas y `App.tsx` 1600. Al agregar algo
  grande, conviene sacarlo a un módulo aparte en vez de engordarlos más.

## Dónde está cada cosa

```
backend/app/
  routers/       un archivo por área; cada endpoint declara su rol requerido
  models.py      SQLAlchemy. Un cambio acá necesita migración de alembic
  schemas.py     Pydantic (entrada/salida de la API)
  auth.py        hash de PIN, tokens y freno de fuerza bruta
  red.py         de qué IP viene una petición (importa detrás de un proxy)
  fechas.py      conversión entre el día del local y el UTC de la base
  respaldos.py   copias de la base (locales y a la carpeta externa del .env)
  ../restaurar_respaldo.py   el otro lado: restaura una copia, con el backend parado
frontend/src/
  App.tsx        el POS (venta, teclado, offline)
  Admin.tsx      backoffice
  db.ts          IndexedDB: catálogo local y cola de ventas offline
  api.ts         cliente HTTP
  sesionLocal.ts acceso al POS cuando no se llega al servidor
  cajaLocal.ts   el turno de caja recordado en el equipo
  sincronizacion.ts  qué hacer con una venta que el servidor rechazó
  components/AuditoriaPanel.tsx  registro de cambios (sub-pestaña de Config)
  components/RespaldosPanel.tsx  copias de la base (sub-pestaña de Config)
```
