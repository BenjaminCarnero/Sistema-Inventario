# Auditoría técnica — Sistema de Inventario y Punto de Venta

**Fecha:** 15 de agosto de 2026
**Alcance:** `backend/` (FastAPI + SQLAlchemy + SQLite) y `frontend/` (React 19 + Vite + Dexie), incluido el trabajo sin commitear en `backend/app/main.py` y `backend/app/config.py`.
**Revisores:** Ingeniería de Ciberseguridad · Arquitectura de Soluciones / Tech Lead.
**Base:** rama `main`, 6 commits por delante de `origin/main`, con cambios sin commitear en el árbol de trabajo.

---

## 1. Resumen ejecutivo

Este no es un proyecto de juguete. El código está por encima del promedio de lo que se ve en un POS de comercio chico: el precio y el total los decide siempre el servidor, las ventas son idempotentes por `uuid_cliente` con índice único, el cobro por QR se confirma contra Mercado Pago con el total del propio servidor, el rol y el estado del usuario se releen de la base en cada request, el freno de fuerza bruta está persistido y distingue el ataque por cuenta del barrido por IP, y hay 245 tests de backend con las migraciones probadas *up/down/up* en CI. No hay una sola consulta SQL construida por concatenación: todo pasa por el ORM, y la batería de payloads de inyección del proyecto lo confirma. Los comentarios del código documentan bugs reales que ya costaron dinero, lo cual es una forma de documentación que casi nadie mantiene y que acá vale mucho.

Dicho eso, **el sistema no está listo para producción todavía**, y la distancia no es de meses: es de una a tres semanas de trabajo enfocado. Hay tres clases de problema. La primera es que el trabajo en curso —servir el frontend compilado desde el mismo backend— **rompe ocho tests de seguridad y CI no se entera**, porque el job de backend nunca compila el frontend y por lo tanto nunca activa el código nuevo. La segunda es un conjunto de defectos de integridad contable que en un POS son más graves que un agujero de seguridad clásico: la hora real de una venta offline se descarta al sincronizar, el stock se puede cambiar sin dejar rastro desde la pantalla de productos, y dos rutas siguen moviendo stock con el patrón leer-modificar-escribir que el propio `CLAUDE.md` documenta como roto en SQLite. La tercera es la ausencia de una capa de operación: no hay reverse proxy, ni gestión de identidad de sesión revocable, ni rate limiting fuera del login, ni cifrado de los respaldos que el README recomienda mandar a OneDrive.

En experiencia de usuario el POS está bien pensado —flujo por teclado, sugerencias de billete, offline real— pero tiene **cero atributos `aria-` en 4.844 líneas de interfaz**, los modales no atrapan el foco ni cierran con Escape, y los mensajes de error se truncan visualmente a una línea justo cuando dicen por qué se rechazó una venta.

**Veredicto:** viable para producción tras cerrar los ocho hallazgos de severidad Alta. Los de severidad Media pueden ir en el mes siguiente sin frenar el despliegue, con la excepción de la zona horaria y el manejo de IP detrás de proxy, que hay que resolver *antes* del primer local con reverse proxy.

---

## 2. Verificación realizada

Todo lo que sigue está comprobado sobre el código, no inferido de la documentación.

| Comprobación | Resultado |
|---|---|
| `pytest -q` (backend, 245 tests) | **8 fallos**, todos por el cambio sin commitear. Ver A-01. |
| `pnpm test` (frontend, 26 tests) | 24 pasan. 2 fallaron en la primera corrida bajo carga y pasaron limpio al repetir: son inestables, no rotos. Ver B-11. |
| Búsqueda de SQL crudo / interpolado | Ninguno. Sólo tres `PRAGMA` literales en `database.py`. |
| Búsqueda de `dangerouslySetInnerHTML` / `innerHTML` / `eval` | Ninguno. |
| `frontend/dist/index.html` presente | Sí — por eso el catch-all está activo en local y CI no lo ve. |

---

## 3. Matriz de riesgos

### 3.1 Severidad ALTA — bloquean el pase a producción

---

#### A-01 · El cambio sin commitear rompe 8 tests de seguridad, y CI está ciego

**Dónde:** `backend/app/main.py:171-185`

El catch-all nuevo devuelve `index.html` con **200** para cualquier ruta que no matchee un router:

```python
@app.get("/{ruta:path}", include_in_schema=False)
def servir_frontend(ruta: str):
    ...
    return FileResponse(_INDEX)
```

Tests que hoy fallan:

```
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[../.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[../../backend/.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[applify_/../../.env.db]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[..%2F..%2F.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[%2e%2e%2f.env]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[/etc/passwd]
FAILED tests/test_seguridad_avanzada.py::TestPathTraversal::test_no_se_baja_cualquier_archivo[applify_....//....//.env.db]
FAILED tests/test_auditoria_y_respaldos.py::TestRespaldoExterno::test_no_se_puede_pedir_un_archivo_de_afuera
```

El test asserta `status_code in (400, 404, 422)` y recibe `200`.

**Precisión importante:** *no* es una lectura de archivos. La validación `_RAIZ in archivo.parents` de `main.py:183` y la de `respaldos.ruta_de()` funcionan bien, incluso con rutas absolutas de Windows y con `..` codificado. El cliente normaliza `/respaldos/../.env` a `/.env`, que ya no matchea el router y cae al catch-all. Lo que se filtra es el `index.html`, no el `.env`.

Pero el impacto real es serio igual:

1. **Toda la API perdió sus 404.** `GET /ventas/cualquier-cosa` ahora responde 200 con HTML. Por eso `api.ts:167-176` ya necesitó una función que detecte "el backend no conoce esta ruta" y "el servidor no devolvió JSON": el síntoma ya se estaba parcheando en el cliente.
2. **Se pierde la señal de detección.** Un WAF o un panel de monitoreo que busque 404 sobre `/etc/passwd` ahora ve 200. El sondeo de traversal se vuelve invisible.
3. **CI da verde con esto roto.** El job `backend` de `.github/workflows/tests.yml` corre `pytest` sin compilar nunca el frontend, así que `frontend/dist/index.html` no existe, el `if` de `main.py:167` es falso, el catch-all no se registra y los ocho tests pasan. En cualquier máquina que haya corrido `pnpm build` —o sea, en producción— fallan. **La suite de seguridad está protegiendo un código que en producción no es el que corre.**

**Corrección:**
- Servir el SPA sólo para peticiones de navegación (`Accept: text/html`) o, mejor, montar los estáticos bajo un prefijo y dejar el fallback sólo para las rutas conocidas del router del cliente (`/`, `/admin`).
- Devolver 404 JSON para todo lo que empiece con un prefijo de API.
- En CI, agregar un paso que cree un `frontend/dist/index.html` mínimo antes de `pytest`, y correr la suite **dos veces**: con y sin frontend compilado. Sin esto, el mismo agujero se vuelve a abrir en el próximo cambio.

---

#### A-02 · `usuarios.nombre` sin UNIQUE + el token identifica por nombre → escalada de privilegios

**Dónde:** `backend/app/models.py:43`, `backend/alembic/versions/76adc741716f_initial_schema.py:22-30`, `backend/app/routers/auth.py:57`, `backend/app/dependencies.py:30`

La columna no tiene índice único ni índice a secas:

```python
nombre = Column(String(100), nullable=False)   # models.py:43
```

La unicidad se valida sólo en código (`routers/auth.py:105` y `:164`), con lectura y después escritura. Y el token guarda el **nombre**, no el id:

```python
data={"sub": user.nombre, "rol": user.rol_id}                       # routers/auth.py:57
user = db.query(models.Usuario).filter(
    models.Usuario.nombre == token_data.username).first()           # dependencies.py:30
```

**Cadena de ataque, sin carrera y sin atacante privilegiado:** un administrador renombra al cajero `juan` a `juan.perez` (operación normal, permitida por `PUT /auth/users/{id}`). Después crea un usuario nuevo llamado `juan` con rol ADMIN. El token que el cajero tiene abierto —válido 12 horas— sigue diciendo `sub: "juan"`, y `dependencies.py:30` ahora lo resuelve al **administrador nuevo**. La sesión del cajero se convirtió en sesión de administrador sin que nadie hiciera nada malicioso.

La variante con carrera (dos `POST /auth/register` simultáneos con el mismo nombre) requiere ser admin, así que es secundaria; la de arriba no requiere nada.

**Corrección:** `sub = str(user.id)`, migración con `UNIQUE` sobre `usuarios.nombre` (previa deduplicación), y resolver el usuario por `id` en `dependencies.py`. El índice además saca el *full scan* que hoy hace cada login.

---

#### A-03 · Cambiar o reiniciar el PIN no corta las sesiones abiertas

**Dónde:** `backend/app/routers/auth.py:184-232` y `:235-266`

El docstring de `cambiar_mi_pin` dice, textualmente, que sin este endpoint "un PIN visto por encima del hombro sólo se podía sacar de circulación borrando la cuenta". Pero el endpoint **no saca nada de circulación**: quien tenga un token válido lo sigue teniendo hasta 12 horas (`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12`). No hay `jti`, ni lista de revocación, ni versión de credencial en el token.

Lo mismo vale para `reiniciar_pin`: un administrador que reinicia el PIN de una cuenta comprometida cree haberla cerrado y no la cerró.

Es contradictorio con una garantía que el sistema **sí** cumple en el resto: el rol y el estado se releen de la base en cada request precisamente para que una baja corte las sesiones. La credencial quedó fuera de ese criterio.

**Corrección:** columna `token_version` (entero) en `usuarios`, incrementada en todo cambio de PIN; incluirla en el token y compararla en `get_current_user`. Es una migración chica y un par de líneas.

---

#### A-04 · Se puede cambiar el stock sin dejar rastro, desde la pantalla de productos

**Dónde:** `backend/app/schemas.py:93`, `backend/app/auditoria.py:18-23`, `backend/app/routers/productos.py:128-165`

`ProductoUpdate` acepta `stock_actual`:

```python
class ProductoUpdate(BaseModel):
    ...
    stock_actual: Optional[int] = None      # schemas.py:93
```

Y la auditoría no lo vigila:

```python
CAMPOS_VIGILADOS = {
    "producto": ("precio_venta", "costo"),   # auditoria.py:19 — falta stock_actual
    ...
}
```

Resultado: `PUT /productos/{id}` con `{"stock_actual": 500}` cambia el inventario **sin generar `MovimientoStock` y sin generar entrada de `Auditoria`**. Cero rastro.

Esto viola directamente una de las reglas que `CLAUDE.md` marca como no negociables: *"Los movimientos de stock se auditan: quién, cuándo y por qué"*. Y anula el propósito declarado del módulo de auditoría, que el propio archivo describe como defensa contra el fraude interno: alcanza con llevarse mercadería y después "corregir" el stock desde la pantalla de edición del producto.

Tampoco se valida que `stock_actual >= 0`: `_validar_producto` (`productos.py:38-44`) sólo acota `precio_venta` y `costo`.

**Corrección:** sacar `stock_actual` de `ProductoUpdate` — el stock ya tiene su camino auditado en `POST /stock/movimientos` con tipo `AJUSTE`. Si por compatibilidad hay que mantenerlo, que genere el `MovimientoStock` correspondiente y una entrada de auditoría, y que valide el signo.

---

#### A-05 · La hora real de una venta offline se descarta al sincronizar

**Dónde:** `frontend/src/db.ts` (`fecha_hora_local`), `frontend/src/App.tsx:360` y `:689-700`, `backend/app/schemas.py:179-196`, `backend/app/models.py:112`

El POS **sí** registra el momento real de la venta:

```ts
fecha_hora_local: new Date().toISOString(),   // App.tsx:360
```

Pero al sincronizar no lo manda (`App.tsx:689-700` arma el payload sin ese campo), `VentaCreate` no tiene dónde recibirlo, y el modelo estampa la hora del servidor:

```python
fecha_hora = Column(DateTime(timezone=True), default=ahora_utc)   # models.py:112
```

**Una venta cobrada a las 20:00 sin red y sincronizada a las 09:00 del día siguiente queda registrada a las 09:00 del día siguiente.** El dato existe en el equipo y se tira a la basura.

Consecuencias en cadena, todas contables:
- El arqueo de `cerrar_caja` (`cajas.py:89-93`) filtra por ventana de tiempo: la venta se cuenta en el turno equivocado, y el turno donde realmente se cobró da faltante de caja.
- `reportes/kpi`, `reportes/ventas_por_dia` y `reportes/ventas_periodo` la asignan al día equivocado.
- `reportes/cajas` y `reportes/cajas/{id}/ventas` la muestran en el turno equivocado.

**Agravante relacionado:** `create_venta` atribuye la venta a `current_user.id`, o sea **a quien sincroniza, no a quien cobró**. Si el turno cambió antes de que vuelva la red, las ventas del cajero saliente quedan a nombre del entrante, y el arqueo de ambos queda mal.

**Corrección:** aceptar `fecha_hora_local` en `VentaCreate`, validarla (no futura, no anterior a *N* días) y usarla como `fecha_hora`. Guardar el `usuario_id` de quien cobró junto con la venta en la cola local y aceptarlo en el alta (con el que sincroniza registrado aparte, para auditoría). Requiere migración.

---

#### A-06 · El bug de stock que ya arreglaron en `ventas.py` sigue vivo en dos rutas más

**Dónde:** `backend/app/routers/devoluciones.py:257-261` y `backend/app/routers/pedidos.py:255-258`

`CLAUDE.md` lo dice sin ambigüedad: *"`with_for_update()` no hace nada en SQLite: compila a un SELECT pelado"*. `ventas.py:185-190` y `stock.py:58-63` ya se corrigieron a UPDATE relativos. Estas dos no:

```python
# devoluciones.py:257
producto = db.query(models.Producto).filter(
    models.Producto.id == producto_id
).with_for_update().first()
if producto:
    producto.stock_actual += cantidad          # leer-modificar-escribir
```

```python
# pedidos.py:255
producto = db.query(models.Producto).filter(
    models.Producto.id == detalle.producto_id
).with_for_update().first()
if producto:
    producto.stock_actual = (producto.stock_actual or 0) + recibida
```

Dos devoluciones del mismo producto en paralelo, o dos recepciones de pedido simultáneas, leen el mismo stock y escriben el mismo valor: **se pierde una**. Es exactamente el bug que documentaron en el comentario de `ventas.py:180-184`, en los dos lugares que quedaron sin migrar. El `with_for_update()` da una falsa sensación de protección.

**Corrección:** el mismo patrón que ya usan:

```python
db.query(models.Producto).filter(models.Producto.id == producto_id).update(
    {models.Producto.stock_actual: models.Producto.stock_actual + cantidad},
    synchronize_session=False,
)
```

---

#### A-07 · Llamada de red a Mercado Pago con la transacción de escritura abierta

**Dónde:** `backend/app/routers/ventas.py:154`, `:258-261`, `:263`; `backend/app/routers/pagos.py:18`

Secuencia dentro de `create_venta`:

1. `db.flush()` (línea 154) → INSERT → SQLite toma lock **RESERVED** y lo mantiene hasta el commit.
2. Se descuenta stock de cada línea (líneas 185-190) → más escrituras bajo el mismo lock.
3. `_confirmar_cobro_por_qr` → `pagos.total_aprobado()` → **HTTPS a Mercado Pago, hasta 8 segundos** (`ESPERA_CONSULTA = RequestOptions(connection_timeout=8.0, max_retries=0)`).
4. `db.commit()` (línea 263).

Con `busy_timeout=10000` en `database.py:35`, **la segunda caja queda esperando hasta 8 segundos por cada cobro con QR de la primera**, y con dos cobros QR encadenados o una red lenta se pasa del timeout y muere con "database is locked" — precisamente lo que WAL vino a evitar y que `database.py:17-29` describe como el problema a resolver.

El comentario de `pagos.py:14-18` muestra que el riesgo se identificó (por eso bajaron el timeout de 180s a 8s), pero se mitigó el síntoma en vez de la causa.

**Corrección:** invertir el orden. Calcular el total en una pasada de sólo lectura (sin `flush`), confirmar el cobro contra Mercado Pago **fuera** de toda transacción de escritura, y recién entonces abrir la transacción que inserta la venta, descuenta el stock y graba la referencia. La unicidad de `pago_referencia` sigue cubriendo la carrera.

---

#### A-08 · Respaldos sin cifrar, con los hashes de PIN, copiados a la nube de un tercero — y descargables sin dejar rastro

**Dónde:** `backend/app/respaldos.py:90-112`, `backend/app/routers/respaldos.py:44-62`, `README.md:335-341`

`_copiar_afuera` hace `shutil.copy2` de la base **en claro** a `RESPALDO_EXTERNO`, y el README recomienda apuntarlo a OneDrive o Google Drive:

```env
RESPALDO_EXTERNO=C:\Users\vos\OneDrive\respaldos-pos
```

Ese archivo contiene el historial completo de ventas, los datos de proveedores y **los hashes bcrypt de todos los PIN**. Con PIN de 4 dígitos para cajeros, un hash bcrypt filtrado es fuerza bruta trivial fuera de línea: no hay freno que valga, porque el atacante ya no pasa por el login.

Además, `GET /respaldos/{nombre}` descarga la base entera y **no genera entrada de auditoría**. El módulo audita cambios de precio, pero la exfiltración total de la base no deja huella. El propio router lo llama "el archivo más sensible del sistema" en su comentario de la línea 12.

**Corrección:**
- Cifrar la copia antes de sacarla del equipo (`age`, `gpg` simétrico, o SQLCipher para toda la base), con la clave fuera de la carpeta sincronizada.
- Registrar en `Auditoria` la creación y **cada descarga** de un respaldo.
- Considerar subir el costo de bcrypt para los PIN cortos, o pasar a un factor de trabajo por rol.

---

### 3.2 Severidad MEDIA

| # | Hallazgo | Ubicación |
|---|---|---|
| **M-01** | **El límite de body se salta con `Transfer-Encoding: chunked`.** El middleware sólo mira `Content-Length`; una petición chunked no lo trae y pasa sin tope. | `main.py:48-63` |
| **M-02** | **Sin rate limiting fuera del login.** No hay `slowapi` ni proxy documentado. `GET /configuracion/marca` es **anónimo** y puede devolver hasta 400 KB (logo en data URI): amplificación barata contra el servidor de un local. | `main.py`, `configuracion.py:83-91`, `:117` |
| **M-03** | **La IP del freno de fuerza bruta sale de `request.client.host`.** Detrás de nginx, Traefik o `tailscale serve` —los tres escenarios del README— todas las peticiones llegan con la IP del proxy: el freno por barrido (`MAX_CUENTAS_POR_IP = 8`) bloquea al local entero con ocho cuentas, o no bloquea a nadie. Falta `ProxyHeadersMiddleware` / `--forwarded-allow-ips`. | `routers/auth.py:25`, `:197`; `auth.py:30` |
| **M-04** | **La zona horaria del comercio es la del reloj del sistema operativo.** `fechas.py` usa `.astimezone()` sin zona explícita. En un contenedor (UTC por defecto) el "día del local" se corre varias horas y el corte del día cae en el horario de mayor venta — el mismo bug que el módulo dice haber arreglado. No existe un setting `ZONA_HORARIA`. Crítico ahora que el objetivo declarado es empaquetar todo en un contenedor. | `fechas.py:25-27`, `:39`; `config.py` |
| **M-05** | **`cerrar_caja` estampa `fecha_cierre` con `func.now()`.** Todo el resto del proyecto usa `ahora_utc()` porque —según `models.py:10-18`— `CURRENT_TIMESTAMP` trunca los microsegundos y "dos eventos del mismo segundo quedaban fuera de rango y el arqueo de caja no contaba esas ventas". `reportes.py:107` filtra `Venta.fecha_hora <= c.fecha_cierre`: una venta del mismo segundo del cierre queda afuera del reporte del turno. Es el bug ya documentado, en el único lugar donde sobrevivió. | `cajas.py:120` |
| **M-06** | **TOCTOU en el control de stock negativo.** Con `permitir_stock_negativo = False`, se lee `producto.stock_actual` y después se descuenta con UPDATE relativo. Dos cajas pasan el chequeo contra el mismo stock y lo dejan negativo igual, que es justo lo que la configuración prometía impedir. | `ventas.py:172-190` |
| **M-07** | **Devoluciones sin idempotencia ni bloqueo.** `_devuelto_por_producto` valida y después escribe, sin índice único ni lock. Dos anulaciones simultáneas de la misma venta devuelven la plata dos veces y reponen el stock dos veces. A diferencia de las ventas, acá no hay `uuid_cliente` que frene el duplicado. | `devoluciones.py:164-193`, `:230-271` |
| **M-08** | **La plata se guarda en `Float`.** `total`, `precio_venta`, `costo`, `subtotal`, `total_devuelto`, `monto_inicial`, `iva_monto`. En un POS el error de redondeo se acumula en el arqueo y en el IVA declarado. Debería ser `Numeric(12,2)` o enteros en centavos. | `models.py:90,91,113,115,116,120,121,146,147,173,196,265,267,268,339` |
| **M-09** | **Faltan índices en las columnas por las que filtra y joinea todo reporte:** `Venta.fecha_hora`, `Devolucion.fecha_hora`, `MovimientoStock.fecha_hora`, `DetalleVenta.venta_id`, `DetalleVenta.producto_id`, `usuarios.nombre`. Hoy son *full scans* que crecen con el historial. | `models.py:112,146,143,171,252,43` |
| **M-10** | **Reportes sin techo de rango ni ventana temporal.** `ventas_periodo` acepta `desde=1900-01-01&hasta=2100-01-01` y carga en memoria todas las ventas, todos sus detalles, **y además** `Usuario.all()`, `Producto.all()` y `Descuento.all()`. `top_productos` y `rentabilidad` agregan sobre el historial completo sin filtro de fecha. | `reportes.py:149-220`, `:67-91`, `:223-263` |
| **M-11** | **N+1 en varias rutas.** Una consulta de producto por línea de venta (`ventas.py:164`) y otra por línea del descuento (`:222`); una consulta de cajero y otra de suma por cada una de las 50 cajas (`reportes.py:100-107`); una de producto por detalle (`reportes.py:338`, `devoluciones.py:85,115`). `read_ventas` no hace `selectinload` de `detalles`: con `limit=500` son 501 consultas. | ver ubicaciones |
| **M-12** | **La cola offline no se reintenta sola.** `syncVentas` se dispara sólo cuando cambia `isOffline` o `isAuthenticated`. Un 500 o un 429 devuelve `'cortar'` y, si la conexión nunca se cae, **la cola queda varada hasta que alguien recargue la pestaña**. El sondeo de `/health` cada 15 s no mueve `isOffline` si el servidor está arriba. | `App.tsx:744-748`, `sincronizacion.ts:36-38` |
| **M-13** | **`processCheckout` se invoca sin `await` y sin `.catch()` en los 7 llamadores.** Si IndexedDB falla (cuota llena, modo privado, perfil corrupto), la promesa se rechaza sin manejar: **el cajero no ve nada y la venta se pierde en silencio**, en el sistema cuya promesa central es no perder una venta. Tampoco hay guarda contra doble clic ni contra Enter repetido: dos ventas por un cobro. | `App.tsx:501,591,1301,1339,1364,1493` |
| **M-14** | **El ticket lo calcula el cliente y nadie lo compara con el del servidor.** El total impreso sale de `App.tsx:332`; la respuesta de `createVenta` se descarta. Con el catálogo local desactualizado —un precio cambió y todavía no resincronizó— el ticket dice un total y la base guarda otro, sin aviso. | `App.tsx:330-332`, `:689` |
| **M-15** | **Tres listas de prefijos de rutas mantenidas a mano, ya desincronizadas.** `PREFIJOS_API` (`main.py:69`), el `proxy` de Vite y los routers reales. **Al proxy de Vite le faltan `/auditoria` y `/respaldos`.** Y si se agrega un router y se olvida el prefijo, esa respuesta de API recibe la CSP permisiva del frontend. | `main.py:69-74`, `vite.config.ts:proxy` |
| **M-16** | **`/auditoria` y `/respaldos` no tienen ninguna pantalla.** Dos módulos completos y con 346 líneas de tests son inalcanzables desde el producto: no hay una sola llamada a esas rutas en `frontend/src`. El respaldo es, según la propia documentación, el riesgo número uno del sistema, y **no hay botón para descargarlo**. La auditoría anti-fraude existe y nadie puede leerla sin curl. | `frontend/src/api.ts` |
| **M-17** | **Token en `localStorage`.** Cualquier XSS se lo lleva. Hoy el riesgo de XSS es bajo (React sin `dangerouslySetInnerHTML`, CSP con `script-src 'self'`), pero la defensa en profundidad pide cookie `HttpOnly` + `SameSite` con protección CSRF. | `api.ts:45,141` |
| **M-18** | **`isAuthenticated` es "hay algo en localStorage".** No se mira `exp`. Con el token vencido se renderiza el backoffice entero y después cada request hace `window.location.reload()`. **En el POS, con carrito cargado, eso pierde el carrito** (es estado de React, no persistido). | `Admin.tsx:79`, `api.ts:55` y ~30 repeticiones |
| **M-19** | **Sin code splitting.** `main.tsx` importa `Admin.tsx` (3.200 líneas) junto con `recharts` y `write-excel-file` en el bundle del POS. La tablet del cajero descarga el backoffice completo, la librería de gráficos y el escritor de Excel para vender. | `main.tsx:5-6` |
| **M-20** | **Cero atributos `aria-` en 4.844 líneas de UI**, con 108 `<button>` y 45 `<label>`. El modal de confirmación no tiene `role="dialog"`, ni `aria-modal`, ni trampa de foco, ni cierre con Escape, ni devolución del foco. Los toasts no tienen `aria-live`: un lector de pantalla nunca anuncia "venta registrada" ni el error. | `App.tsx`, `Admin.tsx`, `UIProvider.tsx:62-115` |
| **M-21** | **Los toasts truncan el mensaje y se cierran a los 3,5 s pase lo que pase.** `truncate` corta a una línea justo los textos que importan —el motivo por el que el servidor rechazó una venta, que el encargado tiene que leer— y el cierre automático fijo incumple WCAG 2.2.1. | `UIProvider.tsx:43`, `:72-76` |

### 3.3 Severidad BAJA

| # | Hallazgo | Ubicación |
|---|---|---|
| **B-01** | `/health` no toca la base: devuelve `ok` con la base corrupta o bloqueada. Sirve de poco para un orquestador, y menos aún para el detector de conexión del POS, que lo sondea cada 15 s. | `main.py:132-134`, `useConexion.ts:31` |
| **B-02** | Sin `GZipMiddleware`. `/productos/catalogo` va sin comprimir y sin `ETag`, y el POS lo pide entero en cada arranque. | `main.py`, `productos.py:55-71` |
| **B-03** | Sin `Cache-Control` en los estáticos nuevos. Los assets con hash podrían ser `immutable`; `index.html` no debería cachearse, o queda una versión vieja de la app tras cada despliegue. | `main.py:184` |
| **B-04** | El `runtimeCaching` del PWA apunta a `https://api.applify.local/`, un host que **no existe en ningún lado del proyecto** (la API es del mismo origen, `API_URL = ''`). Regla muerta: nunca matchea. | `vite.config.ts`, `api.ts:1` |
| **B-05** | La vigencia de descuentos se compara con `datetime.now()` naive contra columnas `DateTime` sin timezone: el único lugar del backend que no usa los helpers de `fechas.py`, contra la regla explícita de `CLAUDE.md`. | `ventas.py:124-128`, `models.py:342-343` |
| **B-06** | El `AJUSTE` de stock lee y después escribe en absoluto: una venta concurrente entre ambos pasos se pierde. Es inherente a un recuento, pero debería resolverse en una sola sentencia. | `stock.py:51,68-69` |
| **B-07** | Logging sin estructura ni correlación: texto plano, sin request-id, sin nivel por entorno. Los logs de acceso guardan IPs sin política de retención (relevante para GDPR/ley de datos personales). | `main.py:17-32` |
| **B-08** | `Auditoria` y `MovimientoStock` crecen sin poda. Sólo `IntentoLogin` se limpia. | `auth.py:111-113` |
| **B-09** | CI sin escaneo de dependencias, sin escaneo de secretos y sin gate de lint (~140 hallazgos conocidos), en un repositorio que **ya tuvo una `SECRET_KEY` filtrada en el historial** y que mantiene la lista negra en el código. | `.github/workflows/tests.yml`, `config.py:16` |
| **B-10** | La puesta en producción está documentada sólo a nivel `.env`. No hay reverse proxy, TLS, servicio del sistema (systemd/NSSM), Dockerfile, workers ni arranque automático; el README enseña `uvicorn --reload`, que no es un modo de producción. | `README.md:317-347` |
| **B-11** | Tests de UI inestables: `admin-pin.test.tsx` falló 2 de 3 bajo carga (timeout de `waitFor`) y pasó limpio al repetir. Con CI cargado va a dar falsos rojos. | `src/tests/admin-pin.test.tsx:100` |
| **B-12** | Ruido en el árbol de trabajo: `claudechatsinterminar.txt` (364 KB, sin trackear y **sin ignorar** — puede terminar en un commit) y `frontend/node_modules_npm_respaldo/`. | raíz, `frontend/` |
| **B-13** | `es-AR` fijo en el formateo mientras el símbolo de moneda es configurable: al cambiar de país el separador de miles queda mal. | `montos.ts:56` |
| **B-14** | El enlace "Admin" está fijo y visible en el POS para cualquier rol, incluido el cajero. | `main.tsx:9-22` |
| **B-15** | `img-src ... https:` en la CSP del frontend permite cargar imágenes de cualquier host HTTPS: canal de exfiltración si alguna vez hay XSS. Es consecuencia de aceptar logos por URL; conviene restringir a los hosts realmente usados. | `main.py:89` |

---

## 4. Lo que está bien y no hay que perder

Vale dejarlo por escrito, porque en una refactorización se rompe sin querer:

- **Sin SQL crudo.** Todo por ORM, sin una sola concatenación. La inyección SQL no es un vector real acá, y la batería de payloads del proyecto lo verifica.
- **El precio y el total los decide el servidor** con el catálogo de la base. `precio_unitario` del cliente es informativo.
- **Ventas idempotentes** por `uuid_cliente` con índice único, y `pago_referencia` único: un pago no respalda dos ventas.
- **El cobro por QR se confirma contra Mercado Pago desde el backend**, con el total que calculó el servidor.
- **Rol y estado se releen de la base en cada request**, no del token: una baja o un cambio de permisos corta las sesiones abiertas.
- **Freno de fuerza bruta persistido** en base, con doble criterio (intentos por cuenta + cuántas cuentas distintas desde una IP) y hash señuelo contra el ataque por cronómetro. El razonamiento del comentario de `auth.py:20-30` es correcto y poco común.
- **Bajas lógicas** en ventas y usuarios; devoluciones que referencian la venta en vez de modificarla.
- **WAL + `busy_timeout` + `foreign_keys=ON`**, con la justificación de por qué `synchronous` se deja en FULL.
- **UPDATE relativos** en `ventas.py` y `stock.py` (ingreso).
- **Validación de arranque que aborta en producción** ante `SECRET_KEY` faltante o comprometida y `CORS_ORIGINS = "*"`.
- **La validación de path traversal es correcta**, tanto en `respaldos.ruta_de()` como en el nuevo `servir_frontend`: resiste `..` codificado, rutas absolutas POSIX y de Windows, y symlinks.
- **245 tests de backend** y migraciones probadas *up/down/up* en CI.
- **El offline es real**: la venta se guarda en IndexedDB antes que nada, y `useConexion` distingue "sin red" de "servidor caído" en vez de confiar en `navigator.onLine`.

---

## 5. Plan de acción

### 5.1 Victorias rápidas — 1 a 3 días, antes de cualquier despliegue

Ordenadas por relación impacto/esfuerzo.

1. **Arreglar el catch-all y darle ojos a CI.** (A-01) — Servir el SPA sólo para peticiones de navegación, devolver 404 JSON en los prefijos de API, y agregar al job de backend un `index.html` de prueba en `frontend/dist/` antes de `pytest`. *Sin este paso, ningún otro arreglo está verificado.*
2. **`sub = user.id` + UNIQUE en `usuarios.nombre`.** (A-02) — Migración con deduplicación previa, cambio en `routers/auth.py:57` y `dependencies.py:30`.
3. **Sacar `stock_actual` de `ProductoUpdate`.** (A-04) — El camino auditado ya existe (`POST /stock/movimientos` con `AJUSTE`).
4. **Los dos UPDATE relativos** en `devoluciones.py:257` y `pedidos.py:255`. (A-06) — Copiar el patrón de `ventas.py:185`.
5. **`ahora_utc()` en lugar de `func.now()`** en `cajas.py:120`. (M-05)
6. **Migración de índices**: `Venta.fecha_hora`, `Devolucion.fecha_hora`, `MovimientoStock.fecha_hora`, `DetalleVenta.venta_id`, `DetalleVenta.producto_id`. (M-09)
7. **Techo de rango en los reportes**: máximo 92 días en `ventas_periodo`, filtro de fecha obligatorio en `top_productos` y `rentabilidad`. (M-10)
8. **`await` + `try/catch` + botón deshabilitado durante el cobro** en los 7 llamadores de `processCheckout`, con toast de error si IndexedDB falla. (M-13)
9. **Accesibilidad mínima del modal y los toasts**: `role="dialog"`, `aria-modal`, foco al abrir y devolución al cerrar, Escape, `aria-live="polite"` en los toasts, y quitar `truncate` de los mensajes de error. (M-20, M-21)
10. **`ProxyHeadersMiddleware` + `--forwarded-allow-ips`** para que el freno de fuerza bruta vea la IP real. (M-03)
11. **`ZONA_HORARIA` explícita en settings**, usada por `fechas.py` en vez del reloj del sistema. (M-04)
12. **`GZipMiddleware`** y `/health` que haga `SELECT 1`. (B-01, B-02)
13. **Sincronizar las listas de rutas**: agregar `/auditoria` y `/respaldos` al proxy de Vite, y derivar `PREFIJOS_API` de `app.routes` en vez de mantenerla a mano. (M-15)
14. **`.gitignore`** para `claudechatsinterminar.txt` y `node_modules_npm_respaldo/`. (B-12)

### 5.2 Mejoras estructurales — 2 a 6 semanas

**Bloque 1 · Integridad contable** (lo más valioso para el negocio)

1. **Preservar la hora y el autor real de la venta offline.** (A-05) — `fecha_hora_local` y `usuario_id` del cajero en `VentaCreate`, con validación de rango y migración. Repasar después arqueo, KPI y reportes.
2. **Dinero a `Numeric(12,2)` o centavos enteros.** (M-08) — Migración con backfill y revisión de todo el cálculo de IVA, descuentos y prorrateo de devoluciones.
3. **Idempotencia y bloqueo en devoluciones.** (M-07) — Clave de idempotencia análoga a `uuid_cliente`.
4. **Resolver el TOCTOU de stock negativo** con `UPDATE ... WHERE stock_actual >= :n` y verificación de filas afectadas. (M-06)

**Bloque 2 · Seguridad de plataforma**

5. **Sesiones revocables**: `token_version` en `usuarios`, incrementada en cada cambio de PIN. (A-03)
6. **Cifrado de respaldos + auditoría de descarga + prueba automática de restauración** en CI o en una tarea programada. (A-08)
7. **Rate limiting** (`slowapi` o el reverse proxy) sobre toda la API, no sólo el login; y cerrar o cachear `/configuracion/marca`. (M-02)
8. **Cerrar el bypass del límite de body** contemplando peticiones chunked. (M-01)
9. **Migrar el token a cookie `HttpOnly` + `SameSite=Strict`** con protección CSRF, y chequear `exp` en el cliente para renovar o avisar antes de cortar. (M-17, M-18)
10. **CI de seguridad**: `pip-audit`, `pnpm audit`, escaneo de secretos (gitleaks) y gate de lint con línea de base para los ~140 hallazgos viejos. (B-09)

**Bloque 3 · Resiliencia y operación**

11. **Reintento con backoff de la cola offline**, independiente del cambio de `isOffline`, más una **pantalla de ventas rechazadas** para que el encargado las resuelva. Hoy se avisa por toast y el registro queda enterrado en IndexedDB. (M-12)
12. **Reconciliar el ticket con la respuesta del servidor**: si el total difiere, avisar en pantalla antes de imprimir. (M-14)
13. **Empaquetado de producción**: Dockerfile multi-stage (compila el frontend, lo copia a `FRONTEND_DIST`), reverse proxy con TLS, servicio del sistema, arranque automático y `--workers` acorde. Es el destino natural del trabajo que ya empezaron en `main.py`. (B-10)
14. **Observabilidad**: logs JSON con request-id, métricas de latencia y de tasa de error, y **alerta cuando falla un respaldo** — hoy ese fallo sólo queda en un `logger.exception` que nadie mira. (B-07)
15. **Camino a PostgreSQL probado**, con matriz de CI SQLite + Postgres, si el objetivo es más de dos cajas. El README ya lo recomienda pero no hay nada que lo verifique.

**Bloque 4 · Producto y mantenibilidad**

16. **Pantallas para auditoría y respaldos.** (M-16) — Dos módulos ya construidos y testeados que el usuario final no puede usar. Es la mejora de mejor relación esfuerzo/valor de toda la lista.
17. **Code splitting con `React.lazy`** para `/admin`, sacando `recharts` y `write-excel-file` del bundle del POS. (M-19)
18. **Capa de servicios/repositorios**: mover la lógica de negocio fuera de los routers (`create_venta` tiene 220 líneas con validación, cálculo de precios, IVA, descuentos, stock y confirmación de pago mezclados) y partir `Admin.tsx` (3.200 líneas) por pestaña.
19. **Auditoría de accesibilidad completa WCAG 2.2 AA**: navegación por teclado en todo el backoffice, contraste, foco visible, etiquetas de formulario. Un POS se opera con teclado por definición; la base para hacerlo bien ya está en el POS y falta en el resto.
20. **Estabilizar los tests de UI** subiendo los timeouts de `waitFor` o usando temporizadores falsos. (B-11)

---

## 6. Prioridad sugerida en una frase

Antes de tocar cualquier otra cosa: **arreglar el catch-all y hacer que CI compile el frontend antes de correr pytest** (A-01). Mientras eso siga así, la suite de seguridad del proyecto está validando un código distinto del que corre en el mostrador, y cualquier otra corrección se hace a ciegas.
