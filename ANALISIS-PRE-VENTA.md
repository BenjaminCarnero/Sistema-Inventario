# Análisis pre-venta — Sistema de Inventario y Punto de Venta

> **Estado al 31/08/2026, después de la tanda de arreglos.** Las 6 fallas
> bloqueantes y 10 de las 12 de severidad media están cerradas y con tests que
> las fijan. Lo que sigue abierto está en la §0. El resto del documento se deja
> **como se escribió durante el análisis**, en pasado: sirve de registro de qué
> se encontró y con qué evidencia, que es lo que hace falta para no reabrirlo.

---

## 0. Qué se arregló y qué quedó abierto

### Cerrado y con test que lo fija

| Era | Ahora |
|---|---|
| **B-01** Escalada de privilegios renombrando un usuario | El token lleva el id (`sub`) y `usuarios.nombre` es UNIQUE |
| **B-02** Cambiar el PIN no cortaba las sesiones | `credenciales_version` en el token: cambiar o reiniciar el PIN corta al instante |
| **B-03** La API perdió todos sus 404 | 404 JSON para los prefijos de API; **CI corre la suite dos veces**, con y sin `dist` |
| **B-04** La venta offline perdía su hora | Viaja `fecha_hora_local`, validada (nada del futuro, nada de más de 30 días) |
| **B-05** Devoluciones y pedidos con el patrón roto | `UPDATE` relativos, como ventas y stock |
| **B-06** Se movía stock sin dejar rastro | `stock_actual` fuera de `ProductoUpdate` |
| **M-01** IP detrás de proxy | `app/red.py` + `PROXIES_CONFIABLES` |
| **M-02** Sin freno fuera del login | `LIMITE_PETICIONES_POR_MINUTO` por IP |
| **M-03** Faltaban 6 índices | Migración `f3c5e7a9b1d4`: todos los `SCAN` pasaron a `SEARCH` |
| **M-04** Descuento con fecha naive | UTC, igual que las columnas |
| **M-05** Zona horaria fija al servidor | `ZONA_HORARIA` configurable |
| **M-06** Reset de config sin auditar | Deja una entrada por parámetro |
| **M-07** No se podía dar de baja un producto | `activo` + `DELETE /productos/{id}` |
| **M-08** Cascada `delete-orphan` en ventas | Sacada |
| **M-10** `/pagos` sin tests | 27 tests propios |
| **M-11** 2 tests inestables | `asyncUtilTimeout` a 5 s |
| **T-54** No se podía entrar sin señal | `sesionLocal.ts`: PBKDF2 del PIN en el equipo |
| **T-55** Auditoría y respaldos sin pantalla | Dos sub-pestañas en Configuración |
| — | Ticket vs. total recalculado: se guarda `total_cobrado` y la diferencia queda auditada |
| — | POS de 1.46 MB → **923 kB** (`React.lazy` para el backoffice) |

**Verificación:** **334 tests de backend** (274 + 60 nuevos) en verde en las
**dos** configuraciones, con y sin frontend compilado. 26 de frontend en verde.
Migraciones probadas *up/down/up*. Tipos limpios. Lint 148, uno menos que antes:
el código nuevo no suma hallazgos.

Un hallazgo nuevo salió de escribir estos tests: **`zoneinfo` no funciona en
Windows sin el paquete `tzdata`**, así que `ZONA_HORARIA` habría quedado sin
efecto y en silencio justo en el sistema operativo donde corre casi toda
instalación de comercio. Se agregó a `requirements.txt`.

### Abierto a propósito

| | Por qué |
|---|---|
| **M-09** Respaldos sin cifrar | Necesita decidir dónde vive la frase de paso. Si se pierde, el respaldo no sirve para nada: es un footgun peor que el problema, y la decisión es tuya |
| **M-12** Dinero en `FLOAT` | Migrar todas las columnas a centavos enteros es grande y el desvío medido es de 5 × 10⁻⁹. Cuando se encare lo fiscal, ahí sí |
| **T-53** Accesibilidad (0 `aria-`) | Es una pasada completa por 7.000 líneas, no un arreglo |
| §6.1 Fiscal, instalador, licencia, impresora | Semanas de trabajo y decisiones de producto |

---

**Fecha:** 31 de agosto de 2026
**Pregunta que responde:** *¿qué le falta a este sistema para salir a la venta?*
**Alcance:** `backend/` (FastAPI + SQLAlchemy + SQLite), `frontend/` (React 19 + Vite + Dexie),
la base `applify.db` en uso, el pipeline de CI y el trabajo sin commitear en `main.py` / `config.py`.
**Método:** 55 comprobaciones ejecutadas contra el código real. Nada de esto está inferido de la
documentación: cada resultado sale de correr algo.

> Existe una auditoría previa (`AUDITORIA-PRODUCCION.md`, 15/08). Este documento es independiente:
> re-verifica sus hallazgos con pruebas propias, confirma cuáles siguen abiertos, corrige el peso de
> algunos y agrega la parte que faltaba: **qué le falta al sistema como producto**, no sólo como código.

---

## 1. Veredicto en una página

El código es bueno. Mejor que el promedio de lo que se ve en un POS de comercio chico, y bastante
mejor de lo que sugiere su tamaño. El precio lo decide siempre el servidor, las ventas son
idempotentes por `uuid_cliente` con índice único, el cobro por QR se confirma contra Mercado Pago con
el total del propio servidor, el rol y el estado del usuario se releen de la base en cada request, el
freno de fuerza bruta está persistido y distingue el ataque por cuenta del barrido por IP, no hay una
sola consulta SQL armada a mano, y hay 274 tests de backend con las migraciones probadas *up/down/up*
en CI. Los comentarios documentan bugs reales que ya costaron plata. Eso vale, y es raro.

**Pero no está listo para salir a la venta, y la distancia tiene dos partes muy distintas.**

**Parte A — defectos técnicos (2 a 3 semanas).** Hay 6 hallazgos que bloquean: una escalada de
privilegios que no necesita atacante (basta con que un administrador renombre a alguien), dos formas
de que un PIN comprometido siga sirviendo 12 horas después de cambiarlo, la API que perdió todos sus
404 por el cambio sin commitear —y CI no se entera—, la hora real de las ventas offline que se
descarta al sincronizar, y dos rutas que mueven stock con el patrón que el propio `CLAUDE.md`
documenta como roto en SQLite.

**Parte B — lo que falta para que sea un producto vendible (2 a 4 meses).** Esto es lo que la
auditoría anterior no miraba y es, comercialmente, lo más caro: **no hay facturación electrónica**
(ni ARCA/AFIP, ni ningún comprobante fiscal), **no hay instalador ni forma de actualizar** una
instalación en un comercio, **no hay licenciamiento**, **no hay soporte de impresora térmica**
(imprime con el diálogo del navegador), **no hay pantalla de auditoría ni de respaldos** aunque el
backend las tenga completas, y **el POS no puede iniciar sesión sin internet**, lo que agujerea la
promesa central del producto.

| | Estado |
|---|---|
| Calidad del código y del diseño de dominio | **Muy buena** |
| Seguridad | **Buena con 4 agujeros concretos**, todos cerrables en días |
| Integridad contable | **3 defectos reales**, uno de ellos silencioso |
| Base de datos | **Correcta pero sin índices**: hoy no se nota, a los 6 meses sí |
| Frontend / UX | **Bien pensado, cero accesibilidad** |
| Operación y despliegue | **Inexistente** |
| Producto vendible | **Le falta lo fiscal, el instalador y el soporte** |

**Recomendación:** cerrar la Parte A y salir con **un local piloto propio o de un conocido**, sin
cobrar. No vender licencias hasta tener resuelto lo fiscal y el instalador: el primer cliente que
pida una factura B y no la pueda emitir es una devolución de plata y una mala referencia.

---

## 2. Cómo se verificó

```
Entorno:  Windows 11 · Python 3.14 (venv) · Node 20 · pnpm 11 · rama main (6 commits por
          delante de origin/main, con cambios sin commitear en app/main.py y app/config.py)
Base:     backend/applify.db — 45 ventas, 72 detalles, 12 productos, 6 usuarios, 11 arqueos
```

| Comando | Resultado |
|---|---|
| `pytest -q` (backend) | **266 pasan / 8 fallan** de 274 |
| `pnpm test` (frontend) | **24 pasan / 2 fallan** de 26 — los 2 pasan al correrlos solos |
| `pnpm build` | **OK** — 1.46 MB (420 KB gzip), 19 entradas precacheadas |
| `pnpm lint` | **149 problemas** (141 errores, 8 avisos) |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` | vacío |
| Tests propios de verificación | 24 pruebas de hallazgo + 5 de concurrencia, escritas y ejecutadas para este informe |

Las pruebas propias se escribieron **para que fallen si el defecto existe**, así el resultado de
pytest *es* la evidencia. Se corrieron y después se borraron: no quedan en el repositorio.

---

## 3. Las 55 comprobaciones

Leyenda: **OK** = el sistema se comporta bien · **FALLA** = defecto confirmado · **AVISO** = correcto
hoy pero frágil.

### 3.1 Seguridad y autenticación (T-01 … T-14)

| # | Qué se probó | Resultado | Evidencia |
|---|---|---|---|
| T-01 | Un token de cajero no puede volverse de administrador | **FALLA** | `GET /auth/users` con el token del cajero → **200** después de un renombrado |
| T-02 | `usuarios.nombre` es único en la base | **FALLA** | Se insertaron 2 usuarios llamados `repetido`; la base los aceptó |
| T-03 | Cambiar el PIN propio corta las sesiones abiertas | **FALLA** | El token anterior sigue devolviendo **200** |
| T-04 | Un admin que reinicia un PIN corta esa sesión | **FALLA** | El token de la víctima sigue devolviendo **200** |
| T-05 | Dar de baja a un usuario corta su sesión | **OK** | 400 inmediato — el estado se lee de la base |
| T-06 | El rol se relee de la base y no del token | **OK** | `dependencies.require_role` consulta en cada request |
| T-07 | La IP real se obtiene detrás de un reverse proxy | **FALLA** | `request.client.host`, sin `X-Forwarded-For` |
| T-08 | Hay freno de peticiones fuera del login | **FALLA** | 60 `GET /productos/` seguidos → 60 × 200 |
| T-09 | Freno de fuerza bruta por cuenta y por barrido de IP | **OK** | Persistido en base, 5 intentos / 8 cuentas por IP |
| T-10 | El login tarda lo mismo exista o no la cuenta | **OK** | Hash señuelo en `auth.verificar_credencial` |
| T-11 | Un token firmado con otra clave se rechaza | **OK** | Suite `test_seguridad_avanzada` |
| T-12 | No hay SQL armado por concatenación | **OK** | Todo por ORM; sólo 3 `PRAGMA` literales en `database.py` |
| T-13 | No hay `dangerouslySetInnerHTML` / `innerHTML` / `eval` | **OK** | 0 ocurrencias en 7.164 líneas de frontend |
| T-14 | `GET /respaldos/{nombre}` no deja salir de su carpeta | **OK (la validación)** | `ruta_de()` resiste `..`, `%2e%2e`, rutas absolutas |

### 3.2 API y ruteo (T-15 … T-20)

| # | Qué se probó | Resultado | Evidencia |
|---|---|---|---|
| T-15 | Una ruta de API inexistente devuelve 404 | **FALLA** | `GET /ventas/no-existe` → **200 `text/html`** |
| T-16 | Una ruta cualquiera inventada devuelve 404 | **FALLA** | **200 `text/html`** (el `index.html` del SPA) |
| T-17 | Cabeceras de seguridad presentes | **OK** | CSP dual API/frontend, HSTS en producción, `X-Frame-Options`, `nosniff` |
| T-18 | CORS no combina `*` con credenciales | **OK** | `allow_credentials` se apaga solo si hay `*` |
| T-19 | Se rechaza un cuerpo de más de 1 MB | **OK** | 413 |
| T-20 | `/docs` y `/openapi.json` cerrados en producción | **OK** | `config.es_produccion` |

### 3.3 Lógica de negocio y contabilidad (T-21 … T-39)

| # | Qué se probó | Resultado | Evidencia |
|---|---|---|---|
| T-21 | El precio sale del catálogo del servidor | **OK** | Se envió `precio_unitario: 1` y se cobró **1000.0** |
| T-22 | Reintentar una venta no la duplica | **OK** | Mismo `uuid_cliente` → mismo id, stock bajó una sola vez |
| T-23 | Un producto en dos líneas no pierde stock | **OK** | 3 + 4 unidades → stock 100 → **93** |
| T-24 | 10 ventas concurrentes del mismo producto | **OK** | 10 hilos → stock exacto, sin unidades perdidas |
| T-25 | La venta descuenta con `UPDATE` relativo | **OK** | `SET stock_actual=(stock_actual - ?)` |
| T-26 | El ingreso de stock suma con `UPDATE` relativo | **OK** | `SET stock_actual=(stock_actual + ?)` |
| T-27 | La devolución repone con `UPDATE` relativo | **FALLA** | `SET stock_actual=97` — **valor absoluto** |
| T-28 | La recepción de pedido suma con `UPDATE` relativo | **FALLA** | `SET stock_actual=110` — **valor absoluto** |
| T-29 | Una venta offline conserva su hora real | **FALLA** | Venta fechada ayer → se guardó con **0 s** de diferencia contra ahora |
| T-30 | La vigencia del descuento usa fechas con zona | **FALLA** | `datetime.now()` naive contra columnas en UTC |
| T-31 | Cambiar el stock desde el producto deja rastro | **FALLA** | `PUT /productos/1 {"stock_actual": 9999}` → 200, **0 movimientos, 0 auditoría** |
| T-32 | Se puede dar de baja un producto | **FALLA** | `DELETE /productos/1` → **405**; el modelo no tiene `activo` |
| T-33 | Restaurar la configuración de fábrica deja auditoría | **FALLA** | `POST /configuracion/restaurar` borra todo sin registrar nada |
| T-34 | Un cajero no ve las ventas de otros | **OK** | Lista vacía |
| T-35 | El catálogo del POS no lleva el costo | **OK** | `ProductoDelCatalogo` no expone `costo` |
| T-36 | El cobro por QR se confirma con el total del servidor | **OK** | Total propio, no el del cliente; 402 si no alcanza |
| T-37 | Un pago no puede respaldar dos ventas | **OK** | `pago_referencia` con índice único + chequeo previo |
| T-38 | Una devolución grande exige administrador | **OK** | Tope configurable, verificado antes de tocar el stock |
| T-39 | El arqueo separa dos cajas abiertas a la vez | **OK** | `devoluciones.caja_turno_id`, con retroceso por ventana para las viejas |

### 3.4 Base de datos (T-40 … T-49)

| # | Qué se probó | Resultado | Evidencia |
|---|---|---|---|
| T-40 | Integridad física y referencial de `applify.db` | **OK** | `integrity_check` → `ok`; `foreign_key_check` → vacío |
| T-41 | Las claves foráneas están activas | **OK** | `PRAGMA foreign_keys` → 1 |
| T-42 | Hay índices en las columnas que se filtran | **FALLA** | Faltan 6: `ventas.fecha_hora`, `ventas.usuario_id`, `detalle_ventas.venta_id`, `movimientos_stock.producto_id`, `movimientos_stock.fecha_hora`, `usuarios.nombre` |
| T-43 | El arqueo y los reportes usan índice | **FALLA** | `SCAN ventas` |
| T-44 | El login busca al usuario por índice | **FALLA** | `SCAN usuarios` en cada intento de acceso |
| T-45 | El detalle de una venta usa índice | **FALLA** | `SCAN detalle_ventas` |
| T-46 | El dinero no se guarda en coma flotante | **FALLA (leve)** | `ventas.total` es `FLOAT`; desvío medido: **5 × 10⁻⁹** sobre 5.000 ventas |
| T-47 | Las migraciones van y vuelven | **OK** | CI corre `upgrade head` → `downgrade base` → `upgrade head` |
| T-48 | La base está en modo WAL | **AVISO** | El archivo hoy está en `delete`; la app lo pone en WAL al conectar |
| T-49 | Borrar una venta no se lleva su detalle | **FALLA (contradicción)** | `cascade='delete,delete-orphan'` en `Venta.detalles` y `Venta.devoluciones` |

### 3.5 Frontend (T-50 … T-55)

| # | Qué se probó | Resultado | Evidencia |
|---|---|---|---|
| T-50 | La suite de vitest pasa entera | **AVISO** | 24/26; los 2 de `admin-pin` pasan al correrlos solos → inestables, no rotos |
| T-51 | El proyecto compila y tipa | **OK** | `tsc -b && vite build` sin errores |
| T-52 | El lint está limpio | **FALLA** | 149 problemas — 118 son `no-explicit-any`, 10 `react-hooks/immutability`, 8 `exhaustive-deps` |
| T-53 | La interfaz es accesible | **FALLA** | **0 atributos `aria-` y 0 `role=`** en 7.164 líneas. `Admin.tsx` no cierra ningún modal con Escape |
| T-54 | El POS puede iniciar sesión sin internet | **FALLA** | `handleLogin` llama a `api.login`, que necesita el servidor |
| T-55 | La auditoría y los respaldos tienen pantalla | **FALLA** | Los routers existen y funcionan; **el frontend no los llama nunca** |

**Resumen: 30 OK · 23 FALLA · 2 AVISO.**

---

## 4. Los que bloquean el pase a producción

### B-01 · Escalada de privilegios sin atacante (T-01, T-02)

**Dónde:** `backend/app/routers/auth.py:57`, `backend/app/dependencies.py:30`, `backend/app/models.py:43`

El token guarda el **nombre** del usuario, y `usuarios.nombre` no tiene `UNIQUE` ni siquiera índice:

```python
data={"sub": user.nombre, "rol": user.rol_id}                    # routers/auth.py:57
user = db.query(models.Usuario).filter(
    models.Usuario.nombre == token_data.username).first()        # dependencies.py:30
nombre = Column(String(100), nullable=False)                     # models.py:43
```

**La cadena no necesita nada malicioso.** Un administrador renombra al cajero `juan` a `juan.perez`
—operación normal, permitida por `PUT /auth/users/{id}`— y después crea un usuario nuevo llamado
`juan` con rol ADMIN. El token que el cajero tiene abierto sigue diciendo `sub: "juan"` y ahora
resuelve al administrador nuevo. **La sesión del cajero se convirtió en sesión de administrador.**

Verificado: el `GET /auth/users` que antes devolvía 403 con ese mismo token pasó a devolver **200**.

**Corrección:** `sub = str(user.id)`, resolver por `id` en `dependencies.py`, y una migración que
agregue `UNIQUE` sobre `usuarios.nombre` previa deduplicación. El índice además saca el *full scan*
que hoy hace cada login (T-44).

### B-02 · Cambiar el PIN no cierra nada (T-03, T-04)

**Dónde:** `backend/app/routers/auth.py:184-232` y `:235-266`

El docstring de `cambiar_mi_pin` dice que sin ese endpoint "un PIN visto por encima del hombro sólo
se podía sacar de circulación borrando la cuenta". Pero el endpoint **no saca nada de circulación**:
no hay `jti`, ni lista de revocación, ni versión de credencial en el token, y los tokens duran 12
horas. Lo mismo con `reiniciar_pin`: el administrador cree haber cerrado una cuenta comprometida y no
la cerró.

Es inconsistente con una garantía que el sistema **sí** cumple: la baja de usuario corta la sesión al
instante (T-05, verificado). La credencial quedó fuera de ese criterio.

**Corrección:** una columna `credenciales_version` en `usuarios`, incluida en el token y comparada en
`get_current_user`. Cambiar o reiniciar el PIN la incrementa. Son ~20 líneas y una migración.

### B-03 · El catch-all del SPA se comió los 404 de toda la API (T-15, T-16)

**Dónde:** `backend/app/main.py:158-185` (sin commitear)

Con `frontend/dist/index.html` presente —o sea, en producción— cualquier ruta que no matchee un
router devuelve **200 con HTML**. Consecuencias verificadas:

1. **La API entera perdió sus 404.** `GET /ventas/cualquier-cosa` → 200 `text/html`. Por eso
   `api.ts:167-176` ya necesitó una función que detecte "el backend no conoce esta ruta": el síntoma
   se estaba parcheando en el cliente.
2. **Se pierde la señal de detección.** Un sondeo de traversal sobre `/etc/passwd` ahora devuelve
   200. Cualquier monitoreo que busque 404 queda ciego.
3. **CI da verde con esto roto.** El job de backend nunca compila el frontend, así que
   `frontend/dist/index.html` no existe, el `if` de `main.py:167` es falso y los 8 tests pasan. **La
   suite de seguridad está protegiendo un código que en producción no es el que corre.**

Precisión importante: **no es una lectura de archivos**. La validación `_RAIZ in archivo.parents`
funciona bien. Lo que se filtra es el `index.html`, no el `.env`.

**Corrección:** devolver 404 JSON para todo lo que empiece con un prefijo de API (la tupla
`PREFIJOS_API` ya existe, sólo hay que usarla también acá), y servir el SPA sólo para peticiones de
navegación. En CI, agregar un paso que cree un `frontend/dist/index.html` mínimo y correr la suite
**dos veces**, con y sin frontend compilado. Sin eso, el agujero se vuelve a abrir en el próximo cambio.

### B-04 · La venta offline pierde su hora real (T-29)

**Dónde:** `frontend/src/db.ts:55`, `frontend/src/App.tsx:360`, `backend/app/schemas.py:180-192`

El POS guarda `fecha_hora_local` en IndexedDB al cobrar, pero `VentaBase` no tiene ese campo, así que
**nunca viaja al servidor**. La venta se registra con `default=ahora_utc`, es decir con la hora en que
se sincronizó.

Verificado: una venta declarada como de ayer se guardó con **0 segundos** de diferencia contra el
momento de la sincronización.

Impacto real, no teórico: un corte de internet el viernes a la tarde manda todas esas ventas al
sábado. **El arqueo del viernes da faltante y el del sábado da sobrante**, el reporte por día miente,
y el cajero del sábado carga con las ventas del viernes. En un producto cuya bandera es "vende sin
red", este es el defecto más caro de la lista.

**Corrección:** agregar `fecha_hora_local: Optional[datetime]` a `VentaCreate`, aceptarla sólo hacia
el pasado y con un techo razonable (no más de N días), y usarla como `fecha_hora`. Mandarla desde
`App.tsx:690` junto con el resto de la venta.

### B-05 · Dos rutas mueven stock con el patrón que el propio proyecto documenta como roto (T-27, T-28)

**Dónde:** `backend/app/routers/devoluciones.py:246-250` y `backend/app/routers/pedidos.py:258`

`CLAUDE.md` dice, textualmente: *"`with_for_update()` no hace nada en SQLite: compila a un SELECT
pelado. Por eso el stock se mueve con UPDATE relativos"*. Las ventas y los ingresos lo cumplen. Estas
dos no:

```python
producto = db.query(models.Producto).filter(...).with_for_update().first()
producto.stock_actual += cantidad                                  # devoluciones.py:249
producto.stock_actual = (producto.stock_actual or 0) + recibida    # pedidos.py:258
```

SQL capturado en vivo, que es la prueba definitiva:

```
[VENTA]          UPDATE productos SET stock_actual=(productos.stock_actual - ?)   ← correcto
[INGRESO]        UPDATE productos SET stock_actual=(productos.stock_actual + ?)   ← correcto
[DEVOLUCION]     UPDATE productos SET stock_actual=?   (97)                       ← pierde escrituras
[PEDIDO RECIBIR] UPDATE productos SET stock_actual=?   (110)                      ← pierde escrituras
```

Dos devoluciones simultáneas del mismo producto, o una devolución mientras entra un pedido, y una de
las dos operaciones desaparece sin ningún error. El inventario queda mal y nadie se entera hasta el
recuento físico.

**Corrección:** el mismo `update({...: columna + n}, synchronize_session=False)` que ya usan
`ventas.py` y `stock.py`. Sacar el `with_for_update()`, que sólo genera falsa confianza.

### B-06 · Se puede mover el stock sin dejar rastro (T-31)

**Dónde:** `backend/app/routers/productos.py:127-165`

`PUT /productos/{id}` acepta `stock_actual` y lo escribe directo. `auditoria.CAMPOS_VIGILADOS` sólo
vigila `precio_venta` y `costo` para productos, así que el cambio **no genera movimiento de stock ni
entrada de auditoría**.

Verificado: `PUT /productos/1 {"stock_actual": 9999}` → 200, el stock quedó en 9999, con **cero**
movimientos nuevos y **cero** entradas de auditoría.

Esto anula la regla del dominio *"los movimientos de stock se auditan: quién, cuándo y por qué"*, y
es exactamente el hueco por el que se tapa un faltante: contar mal, ajustar el número a mano desde la
pantalla de productos, y que el historial no muestre nada.

**Corrección:** sacar `stock_actual` de `ProductoUpdate`. El stock se mueve por `/stock/movimientos`,
que ya hace lo correcto y ya exige rol de encargado o admin.

---

## 5. Lo que hay que arreglar en el mes siguiente

| # | Hallazgo | Dónde | Por qué importa |
|---|---|---|---|
| M-01 | Sin `X-Forwarded-For`, detrás de un proxy todas las cajas comparten IP (T-07) | `routers/auth.py:26` | El freno por barrido bloquearía a todo el local, y el freno por cuenta se vuelve inútil. **Hay que resolverlo antes del primer local con reverse proxy** |
| M-02 | No hay rate limiting fuera del login (T-08) | `main.py` | 60 peticiones seguidas pasan sin freno. Un cliente con un bucle roto tumba la caja |
| M-03 | Faltan 6 índices en columnas calientes (T-42 … T-45) | migraciones | Hoy con 45 ventas no se nota. A los 50.000 tickets el dashboard y el arqueo escanean la tabla entera en cada consulta |
| M-04 | La vigencia del descuento usa hora local naive (T-30) | `routers/ventas.py:120` | Un descuento "hasta hoy" se vence a la hora equivocada. Es el mismo bug que `fechas.py` ya arregló en todos lados menos acá |
| M-05 | Sin zona horaria configurable | `app/fechas.py` | El "día del local" es el del reloj del servidor. Un VPS en UTC corta el día a las 21:00 hora argentina |
| M-06 | `POST /configuracion/restaurar` borra todo sin auditar (T-33) | `routers/configuracion.py:207` | Alguien puede resetear el IVA y los topes de devolución sin dejar rastro |
| M-07 | No se puede dar de baja un producto (T-32) | `models.py`, `routers/productos.py` | El catálogo sólo crece. Un producto discontinuado sigue apareciendo en el POS para siempre |
| M-08 | `delete-orphan` en `Venta.detalles` (T-49) | `models.py:139-140` | Contradice "las ventas no se borran". Hoy nada las borra, pero la cascada está armada esperando a que alguien agregue el endpoint |
| M-09 | Los respaldos no se cifran | `app/respaldos.py` | El README recomienda mandarlos a OneDrive. Ese archivo tiene las ventas y todos los PIN hasheados |
| M-10 | El router `/pagos` no tiene tests propios | `tests/` | La lógica de MP dentro de `/ventas` **sí** está probada (con monkeypatch). Lo que no se prueba nunca es el parseo de la respuesta del SDK, el timeout y la creación de preferencia |
| M-11 | 2 tests de frontend inestables bajo carga (T-50) | `src/tests/admin-pin.test.tsx` | Un CI que falla al azar deja de mirarse a la tercera vez |
| M-12 | Dinero en `FLOAT` (T-46) | `models.py` | **Severidad baja, y conviene decirlo con honestidad:** el desvío medido es de 5 × 10⁻⁹ sobre 5.000 ventas. No pierde plata en este volumen. Es deuda a resolver si alguna vez se migra a otro motor o se factura |

---

## 6. Lo que le falta para ser un producto que se pueda vender

Esta sección es la que responde de verdad a la pregunta. Los defectos de arriba se arreglan en
semanas. Esto es lo que separa "un sistema que anda" de "un sistema que se le puede cobrar a alguien".

### 6.1 Bloqueantes comerciales

**No hay facturación electrónica. Ninguna.**
Búsqueda exhaustiva en `backend/app`, `frontend/src` y `README.md`: **cero** referencias a AFIP/ARCA,
a `CAE`, a punto de venta fiscal o a tipos de comprobante. `cuit` aparece únicamente como un campo de
texto en la ficha del proveedor. El sistema emite un ticket interno, no un comprobante.

Eso limita el mercado a comercios que no necesitan facturar —cada vez menos— y es la primera pregunta
que hace cualquier comprador. Implementar WSFEv1 (certificado, homologación, tipos A/B/C, notas de
crédito para las devoluciones que ya existen) es entre **4 y 8 semanas**, y hay que hacerlo bien
porque un comprobante mal emitido es un problema del cliente con el fisco, no un bug.

*Alternativa realista para salir antes:* vender explícitamente como **sistema de gestión e inventario
con ticket no fiscal**, integrable después. Es un producto legítimo y más chico, pero hay que decirlo
en la propuesta comercial, no descubrirlo en la demo.

**No hay forma de instalar ni de actualizar.**
No existe `Dockerfile`, ni `docker-compose`, ni servicio de Windows, ni instalador, ni script de
puesta en marcha. La instalación de hoy es el README: clonar el repo, crear un venv, correr alembic,
levantar uvicorn a mano y `pnpm dev` en otra consola. Eso lo puede hacer quien escribió el código; no
lo puede hacer el dueño de una verdulería, y no lo podés repetir en veinte locales.

Y lo más importante: **no hay historia de actualización**. Si en el local 7 hay que arreglar el bug de
la hora de las ventas offline, hoy no hay ningún mecanismo para llevar ese arreglo hasta esa máquina.

*Mínimo indispensable:* un ejecutable o un servicio de Windows que levante backend y frontend juntos
(el trabajo sin commitear de servir el `dist` desde FastAPI va justo en esa dirección — es la decisión
correcta, sólo hay que terminarla), y un comando de actualización que corra `alembic upgrade head`.

**No hay licenciamiento ni control de instalaciones.**
No hay `LICENSE`, ni clave de activación, ni forma de saber cuántas instalaciones hay ni de darlas de
baja. Un cliente que deja de pagar sigue usando el sistema, y el código está en su máquina.

**No hay soporte de impresora térmica.**
Los tres puntos de impresión (`App.tsx:1629`, `Admin.tsx:1355` y `:3189`) usan `window.print()`, o sea
el diálogo del navegador. Ningún comercio imprime tickets así: usan una térmica de 58 u 80 mm por USB
o red, con corte automático y apertura de cajón. Sin eso, la caja no cierra físicamente.

### 6.2 Funcionalidad que el backend ya tiene y nadie puede usar

Esto es plata ya invertida que no rinde:

- **`/auditoria` está completo, con filtros por entidad, usuario y rango de fechas. El frontend no lo
  llama nunca** (T-55). Toda la trazabilidad de cambios de precio —el argumento de venta contra el
  fraude interno— es invisible.
- **`/respaldos` está completo**: listar, crear, descargar. Tampoco tiene pantalla. El único respaldo
  que existe es el automático al cerrar caja, y el dueño no tiene forma de bajarse una copia.
- El proxy de desarrollo de Vite **no incluye `/auditoria` ni `/respaldos`**
  (`vite.config.ts:52-68`), así que el día que se agreguen esas pantallas van a fallar en desarrollo
  con un error confuso. Trampa puesta y esperando.

Son dos pestañas en `Admin.tsx`. Probablemente **dos días de trabajo** para desbloquear dos de las
funciones más vendibles del sistema.

### 6.3 La promesa central tiene un agujero

`CLAUDE.md` lo dice como regla que no se negocia: *"El POS tiene que poder vender sin red"*. Es cierto
**mientras haya una sesión abierta**. Pero `handleLogin` (`App.tsx:149`) llama a `api.login`, que
necesita el servidor. El token dura 12 horas.

Traducido: el comercio abre a las 8 de la mañana, el internet está caído, la sesión de ayer venció, y
**el POS no vende**. Es el escenario exacto que el producto promete cubrir. Peor aún, el mensaje que
ve el cajero en ese caso es "Credenciales incorrectas", porque `api.ts:41` trata cualquier fallo como
credencial mala.

*Corrección posible:* guardar en el equipo un hash del PIN del último usuario que entró bien, y
permitir el acceso offline contra ese hash con permisos acotados (vender sí, backoffice no). Es un
compromiso de seguridad consciente, y hay que documentarlo, pero sin algo así la promesa no se cumple.

### 6.4 Accesibilidad y usabilidad

- **Cero atributos `aria-` y cero `role=`** en 7.164 líneas de interfaz (T-53). Ningún modal atrapa el
  foco; `Admin.tsx` no cierra ninguno con Escape. Para vender al Estado o a una cadena, esto es un
  requisito de pliego, no una mejora.
- **Un solo bundle de 1.46 MB** (420 KB comprimido). `Admin.tsx` —164 KB de código fuente, el
  backoffice completo— se descarga también en la tablet del cajero, que nunca lo va a abrir. Se
  arregla con un `React.lazy` en la ruta de admin.
- La regla de caché del service worker apunta a `https://api.applify.local`
  (`vite.config.ts:104`), un host que no existe: la API se sirve del mismo origen. **Esa
  configuración no hace nada.** No rompe (el precache de los assets sí funciona), pero da una
  sensación falsa de que las respuestas de la API están cacheadas.

### 6.5 Operación

No hay reverse proxy documentado, ni certificado TLS que no sea autofirmado, ni monitoreo, ni alertas,
ni rotación de la `SECRET_KEY`, ni un procedimiento de qué hacer cuando un local llama. Los logs
rotan a disco (bien) pero nadie los mira desde afuera. **Cuando tengas cinco clientes, esto es tu
trabajo de todos los días** si no lo resolvés antes.

---

## 7. Plan de trabajo sugerido

### Semana 1 — cerrar los bloqueantes de seguridad
- [ ] `sub = user.id` + `UNIQUE` en `usuarios.nombre` + resolver por id **(B-01, y de paso T-44)**
- [ ] `credenciales_version` en el token para revocar sesiones al cambiar el PIN **(B-02)**
- [ ] 404 JSON para los prefijos de API + doble corrida en CI con y sin `dist` **(B-03)**
- [ ] `X-Forwarded-For` con lista de proxies de confianza **(M-01)**

### Semana 2 — cerrar los bloqueantes contables
- [ ] `fecha_hora_local` viaja del POS al servidor y se valida **(B-04)**
- [ ] `UPDATE` relativo en devoluciones y en recepción de pedidos **(B-05)**
- [ ] Sacar `stock_actual` de `ProductoUpdate` **(B-06)**
- [ ] Migración con los 6 índices faltantes **(M-03)**
- [ ] Zona horaria configurable y fecha del descuento con `timezone` **(M-04, M-05)**

### Semana 3 — hacerlo instalable y usable
- [ ] Terminar el servido del `dist` desde FastAPI: un puerto, un proceso
- [ ] Servicio de Windows + comando de actualización que corra las migraciones
- [ ] Pestañas de **auditoría** y **respaldos** en `Admin.tsx` (§6.2)
- [ ] Agregar `/auditoria` y `/respaldos` al proxy de Vite
- [ ] `React.lazy` para el backoffice

### Semanas 4 a 6 — piloto
- [ ] Un local real, sin cobrar, con vos mirando los logs todos los días
- [ ] Impresora térmica (ESC/POS)
- [ ] Login offline contra el hash local
- [ ] Rate limiting general, cifrado de respaldos, pasada de accesibilidad

### Meses 2 a 4 — producto vendible
- [ ] Facturación electrónica ARCA/AFIP, o decisión explícita de vender sin ella
- [ ] Licenciamiento y activación
- [ ] Documentación de operación y canal de soporte
- [ ] Recién ahí, cobrar

---

## 8. Anexo — evidencia cruda

### Los 8 tests que fallan hoy en `pytest`

```
FAILED tests/test_auditoria_y_respaldos.py::TestRespaldoExterno::test_no_se_puede_pedir_un_archivo_de_afuera
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[../.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[../../backend/.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[applify_/../../.env.db]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[..%2F..%2F.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[%2e%2e%2f.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[/etc/passwd]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[applify_....//....//.env.db]
```

Los 8 son el mismo defecto: **B-03**. Todos esperan `400/404/422` y reciben `200`.
Ninguno es una lectura de archivos: lo que se devuelve es el `index.html`.

### Fallos de las pruebas propias (cada fallo = un defecto confirmado)

```
ESCALADA CONFIRMADA: el token del cajero devolvio 200
DUPLICADO CONFIRMADO: hay 2 usuarios llamados 'repetido'
SESION NO REVOCADA: el token viejo sigue sirviendo (200)
SESION NO REVOCADA tras reinicio de PIN (200)
SIN SOPORTE DE PROXY: la IP sale de request.client.host
SIN RATE LIMIT: 60 peticiones seguidas devolvieron {200}
404 PERDIDO: devolvio 200 (text/html; charset=utf-8)
HORA PERDIDA: se guardo con la hora de sincronizacion (dif 0s)
FECHA NAIVE: la vigencia del descuento usa hora local
PATRON ROTO: la devolucion lee y suma en Python
STOCK SIN RASTRO: se cambio a 9999 sin movimiento de stock ni auditoria
SIN INDICE: ventas.fecha_hora, ventas.usuario_id, detalle_ventas.venta_id,
            movimientos_stock.producto_id, movimientos_stock.fecha_hora, usuarios.nombre
DINERO EN COMA FLOTANTE: ventas.total es FLOAT
CASCADA ACTIVA: borrar una venta se lleva sus detalles
```

### Planes de consulta sobre `applify.db`

```
arqueo / reportes por fecha     → SCAN ventas
login por nombre de usuario     → SCAN usuarios
detalle de una venta            → SCAN detalle_ventas
top de productos (join)         → SCAN d + USE TEMP B-TREE FOR GROUP BY
movimientos por producto        → SCAN movimientos_stock
ventas de un cajero             → SCAN ventas
devoluciones de una venta       → SEARCH USING INDEX ix_devoluciones_venta_id   ← el único bien
```

### SQL emitido al mover stock

```
[VENTA]           UPDATE productos SET stock_actual=(productos.stock_actual - ?) WHERE id = ?
[INGRESO STOCK]   UPDATE productos SET stock_actual=(productos.stock_actual + ?) WHERE id = ?
[DEVOLUCION]      UPDATE productos SET stock_actual=?  -- (97)
[PEDIDO RECIBIR]  UPDATE productos SET stock_actual=?  -- (110)
```

### Estado de la base en uso

```
integrity_check   ok
foreign_key_check (vacío)
journal_mode      delete     ← la app lo pone en WAL al conectar
ventas 45 · detalle_ventas 72 · movimientos_stock 79 · productos 12 · usuarios 6
cajas_turnos 11 · auditoria 11 · pedidos 5 · devoluciones 0 · intentos_login 0
```

### Compilación y calidad del frontend

```
vite build        ✓ 2910 módulos · 4.34 s
  index.js        1.463,19 kB  (gzip 420,55 kB)   ← un solo chunk
  index.css          33,74 kB  (gzip   6,78 kB)
  PWA precache    19 entradas (1.616 KiB)

eslint            149 problemas (141 errores, 8 avisos)
  118  @typescript-eslint/no-explicit-any
   10  react-hooks/immutability
    8  react-hooks/exhaustive-deps
    5  react-hooks/set-state-in-effect
    4  react-refresh/only-export-components
    3  @typescript-eslint/no-unused-vars
    1  react-hooks/purity

aria-*  0     role=  0     Escape en Admin.tsx  0
```

> Nota sobre el lint: `CLAUDE.md` advierte que estos ~140 hallazgos son viejos y que no hay que
> tomarlos como algo recién roto. Es correcto. Pero 118 `any` en el cliente HTTP y en la exportación a
> Excel son 118 lugares donde el compilador dejó de ayudar, justo en el código que maneja las
> respuestas del servidor. Para un producto que se vende, vale la pena tiparlos.

---

## 9. Cierre

Lo mejor que tiene este proyecto no es una función: es que **las decisiones difíciles ya están
tomadas y bien tomadas**. El precio en el servidor, la idempotencia por UUID, el arqueo por turno, el
freno que distingue el ataque del cajero con mala mañana, los comentarios que explican qué bug costó
cada línea. Eso no se improvisa y es lo que hace que los defectos de este informe sean todos
arreglables en semanas, y no un rediseño.

Lo que falta es casi todo lo que está **alrededor** del código: instalarlo, actualizarlo, facturarlo,
imprimirlo y sostenerlo cuando llame un local un martes a las nueve de la mañana.

**Un camino concreto:** tres semanas para la Parte A, un piloto real sin cobrar durante un mes, y la
decisión sobre lo fiscal tomada antes de la primera propuesta comercial. Si esa decisión es "salgo sin
facturación electrónica", que quede escrito en la propuesta.
