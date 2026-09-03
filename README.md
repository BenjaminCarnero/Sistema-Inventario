# Sistema de Inventario y Punto de Venta

Punto de venta e inventario para comercios chicos. Funciona **sin internet**: el
cajero sigue vendiendo aunque se caiga el wifi o el servidor, y las ventas se
sincronizan solas cuando vuelve la conexión.

Pensado para operar **sin mouse**: el lector de código de barras escribe en el
campo de código y con Enter se encadena toda la venta.

---

## Qué hace

**Punto de venta**
- Lector de código de barras por cámara o lector USB
- Operación completa por teclado (flechas y Enter)
- Cobro en efectivo con cálculo de vuelto, tarjeta, transferencia y Mercado Pago QR
- Ticket imprimible en 80 mm y envío por WhatsApp
- Descuentos por porcentaje o monto fijo, globales o por producto
- **Modo sin conexión**: vende, guarda y sincroniza al volver la red

**Backoffice**
- Catálogo con imágenes, categorías, búsqueda, filtros y etiquetas de código de barras
- Entrada de mercadería y ajuste por recuento físico
- Registro completo de movimientos de stock: quién, cuándo y por qué, exportable a Excel
- Reposición: proveedores, pedidos por WhatsApp y carga del stock al recibirlos
- Devoluciones parciales y anulación de ventas: reponen el stock y descuentan de la caja
- Alertas de stock bajo
- Reportes: recaudación diaria, productos más vendidos, rentabilidad y arqueos de caja
- Exportación a Excel por rango de fechas
- Gestión de usuarios con tres roles: administrador, encargado y cajero
- Cada uno cambia su propio PIN, y el administrador reinicia el de quien se lo olvidó
- Copias de la base en cada cierre de caja, con duplicado fuera del equipo

**Configurable sin tocar código**
- Logo, colores y nombre del comercio (white-label)
- Impuestos: alícuota, nombre e incluido en el precio o sumado al cobrar
- Moneda, métodos de pago habilitados, topes de efectivo y textos del ticket

---

## Requisitos

- **Python 3.11+** ([descargar](https://www.python.org/downloads/))
- **Node.js 20+** ([descargar](https://nodejs.org/))

No hace falta instalar ninguna base de datos: por defecto usa SQLite, que es un
solo archivo.

---

## Instalación

### 1. Clonar

```bash
git clone https://github.com/BenjaminCarnero/Sistema-Inventario.git
cd Sistema-Inventario
```

### 2. Backend

```bash
cd backend
python -m venv venv
```

Activar el entorno:

```bash
venv\Scripts\activate
```

En Linux o macOS es `source venv/bin/activate`.

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

### 3. Configurar las credenciales

Copiá el archivo de ejemplo:

```bash
copy .env.example .env
```

Generá una clave de firma y pegala en `SECRET_KEY` dentro del `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> El `.env` no se sube al repositorio. Es el único lugar donde viven las
> credenciales.

### 4. Crear la base y el primer usuario

```bash
alembic upgrade head
python seed_admin.py
```

El script pide el PIN por teclado. No hay usuario ni contraseña por defecto.

### 5. Levantar el backend

```bash
uvicorn app.main:app --reload --port 8001
```

Queda escuchando en `http://127.0.0.1:8001`. La documentación interactiva está
en `/docs` (sólo en modo desarrollo).

### 6. Frontend

En **otra terminal**:

```bash
cd frontend
pnpm install
node scripts/servidor.mjs
```

Abrí `http://localhost:5173`. El punto de venta está en `/` y el backoffice en
`/admin`.

Las dependencias se manejan con [pnpm](https://pnpm.io). A diferencia de npm,
no ejecuta los scripts de instalación de las dependencias salvo que se los
autorice de forma explícita, que es por donde entran la mayoría de los ataques
a la cadena de suministro.

Si no lo tenés instalado, la forma de conseguirlo sin depender de npm es bajar
el binario de las [releases oficiales](https://github.com/pnpm/pnpm/releases).

### 7. Entrar desde el celular o una tablet

El servidor ya escucha en toda la red local. Al levantarlo, Vite imprime algo así:

```
➜  Local:   http://localhost:5173/
➜  Network: http://192.168.1.106:5173/
```

Esa dirección de **Network** es la que se abre desde el celular, con el celular
conectado a la misma red wifi que la computadora. La computadora tiene que
quedar prendida con las dos terminales corriendo: es la que tiene la base.

Sólo hace falta abrir el puerto 5173. El backend sigue atado a `127.0.0.1` y no
se expone: el navegador le pega a la API con rutas relativas y Vite hace de
intermediario.

Si el celular no carga la página, es el Firewall de Windows bloqueando la
conexión entrante. La primera vez Windows suele preguntar; si le diste que no,
hay que permitir Node.js en redes privadas desde *Firewall de Windows Defender ›
Permitir una aplicación*.

**La cámara no funciona así.** Los navegadores sólo prestan la cámara en
`localhost` o con HTTPS, así que entrando por la IP el escáner queda
deshabilitado y la pantalla lo avisa. Se puede vender igual escribiendo el
código o con un lector bluetooth. Para tener la cámara hace falta servir la app
por HTTPS.

### 8. Con HTTPS, para que ande la cámara (opcional)

Hay dos caminos. El primero funciona siempre; el segundo es más prolijo pero
depende de que tu cuenta de Tailscale lo permita.

#### Certificado propio

Una sola vez:

```bash
cd frontend
bash scripts/generar-certificado.sh
```

Y para levantar el servidor por HTTPS:

```bash
node scripts/servidor.mjs --https
```

Se entra desde el celular a `https://<la-ip>:5173`. Como el certificado está
firmado por vos y no por una autoridad conocida, **la primera vez el navegador
avisa que el sitio no es de confianza**: hay que entrar igual (*Configuración
avanzada › Continuar*). Después queda aceptado.

El certificado incluye las IPs que tenía la computadora al generarlo. Si cambia
la IP, hay que volver a generar el certificado.

El servidor normal (`node scripts/servidor.mjs`, sin `--https`) sigue andando
por HTTP, sin advertencias. La clave privada queda en `frontend/certs/`, que
está en el `.gitignore`.

#### Tailscale

[Tailscale](https://tailscale.com) arma una red privada entre tus dispositivos
y emite un certificado de verdad, así que no hay ninguna advertencia. Requiere
habilitar **Serve** y **HTTPS Certificates** en la consola de administración, y
tener la aplicación instalada en la computadora y en el celular con la misma
cuenta. Después, con el servidor corriendo:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:5173
```

`tailscale serve status` muestra la dirección `https://…​.ts.net` que queda
publicada.

Es **`serve`, no `funnel`**: la app queda visible únicamente para tus propios
dispositivos, no para internet. Nunca uses `funnel` con este sistema — dejaría
la caja del negocio abierta al mundo.

---

## Cómo se usa

### Vender

| Tecla | Qué hace |
|---|---|
| Código + **Enter** | Agrega el producto al carrito |
| **Enter** con el campo vacío | Abre el cobro |
| **↑ ↓** | Elegir una línea del carrito |
| **+** / **−** | Sumar o restar unidades |
| **Supr** | Quitar la línea |
| **↑ ↓** y **Enter** | Elegir y confirmar el método de pago |
| **Enter** en efectivo | Cobra; con el campo vacío asume importe justo |
| **Enter** en el ticket | Cierra e inicia la venta siguiente |
| **Esc** | Volver o cancelar |
| **F1** | Ver todos los atajos |

El foco vuelve solo al campo de código, así el lector siempre funciona.

### Sin conexión

Si se cae internet o el servidor, el POS lo detecta y avisa. Se puede seguir
vendiendo: las ventas se guardan en el equipo y el encabezado muestra cuántas
faltan enviar. Al volver la conexión se sincronizan solas, sin duplicarse.
Cada venta viaja con la hora en que se cobró de verdad, así una tarde sin
internet no le mueve las ventas al día siguiente ni descuadra dos arqueos.

**También se puede entrar sin conexión.** Quien ya haya iniciado sesión alguna
vez en ese equipo puede volver a entrar con su mismo PIN aunque no haya
servidor: el acceso se valida contra el propio equipo. Sirve para vender y no
para el panel de administración, y vale hasta 30 días desde la última vez que
el equipo habló con el servidor. Un dispositivo nuevo, o alguien que nunca
entró ahí, sí necesita señal la primera vez.

Mercado Pago no aparece mientras no haya conexión, porque necesita el servidor.

Si un precio cambió mientras el equipo estaba sin señal, el ticket que se le dio
al cliente puede no coincidir con lo que queda registrado: manda el precio del
servidor, y la diferencia aparece en **Configuración → Registro de cambios**.

**Un corte de luz es otra cosa**: ahí se apaga el equipo. Conviene una UPS para
la PC y el router, o trabajar desde una tablet con datos móviles.

### Cargar mercadería y corregir el stock

En **Admin › Catálogo**, el botón junto a cada producto abre dos operaciones:

- **Entró mercadería**: suma las unidades que llegaron del proveedor.
- **Recuento físico**: el stock queda en lo que contaste, y el sistema guarda la
  diferencia contra lo que decía. Sirve después de un inventario.

Las dos quedan registradas con el usuario, la fecha y el motivo. Las salidas no
se cargan a mano: las genera la venta.

El registro completo está en **Admin › Movimientos de Stock**: todo lo que entró
y salió del depósito, filtrable por producto, por tipo y por rango de fechas, y
exportable a Excel. Es lo que se mira para auditar el inventario cuando los
números no cierran.

### Reponer mercadería

En **Admin › Reponer** está lo que falta, agrupado por proveedor, porque el
pedido se hace por proveedor y no por producto.

1. Cargá los proveedores con su teléfono de WhatsApp (botón **Proveedores**).
2. Asigná el proveedor a cada producto, desde su ficha o desde la misma
   pantalla de reposición.
3. Poné cuánto pedís de cada uno y tocá **Armar pedido**. Si el producto tiene
   una **cantidad habitual** configurada, el campo viene precargado con ella.
4. El sistema arma el mensaje y lo abre en WhatsApp, o lo copiás para mandarlo
   por donde quieras. El texto se configura en Configuración.
5. Cuando llega la mercadería, **Recibí esto**: podés corregir las cantidades
   si vino menos de lo pedido, y entra todo al stock de una sola vez.

Mientras el pedido está en camino, el producto muestra cuántas unidades ya
pediste. Es lo que evita pedir dos veces lo mismo.

Los productos sin proveedor no se esconden: aparecen en su propio grupo con el
aviso, así la pantalla sirve desde el primer día aunque no hayas cargado
todavía ninguna ficha.

### Devolver o anular una venta

En **Admin › Reportes y Cajas**, al abrir el detalle de un turno cada venta tiene
**Anular / Devolver**. Se puede devolver una parte o la venta entera.

La venta nunca se borra: queda registrada y la devolución la referencia, así el
historial es auditable. La mercadería vuelve al stock, y lo devuelto en efectivo
se descuenta del arqueo del turno. El importe se calcula sobre lo realmente
cobrado, de modo que el descuento y el impuesto quedan repartidos.

Sólo el administrador y el encargado pueden hacerlo: mueve plata de la caja.

### Categorías

En **Admin › Catálogo › Categorías** se agrupan los productos. Sirven para
filtrar el catálogo en el backoffice y en la pantalla de venta. Borrar una
categoría no borra sus productos: quedan sin categoría.

### Configurar el negocio

En **Admin › Configuración › Parámetros del sistema** se cambian el logo, los
colores, el IVA, la moneda, los métodos de pago y los textos del ticket. Los
cambios llegan al POS de todos los cajeros apenas se guardan.

Los valores de fábrica son para Argentina: IVA 21% ya incluido en el precio y
pesos argentinos. Para otro país alcanza con cambiar la alícuota, el nombre del
impuesto y la moneda.

---

## Puesta en producción

Antes de usarlo con plata de verdad, en el `.env`:

```env
ENTORNO=produccion
SECRET_KEY=<una clave larga y propia>
CORS_ORIGINS=["https://tu-dominio.com"]
FRONTEND_URL=https://tu-dominio.com
RESPALDO_EXTERNO=C:\Users\vos\OneDrive\respaldos-pos
PROXIES_CONFIABLES=1        # si hay un nginx / Caddy adelante
```

> **`PROXIES_CONFIABLES` no es opcional si vas a poner un reverse proxy.** Con
> 0, todas las peticiones llegan con la IP del proxy: el freno contra el barrido
> de cuentas bloquearía a todo el local de una y el freno por cuenta dejaría de
> distinguir a nadie. Poné la cantidad de proxies propios que hay delante.

Con `ENTORNO=produccion` el arranque **falla** si falta la `SECRET_KEY`, si
`CORS_ORIGINS` está en `"*"` o si `FRONTEND_URL` quedó apuntando a localhost;
además se oculta la documentación de la API y se activa HSTS.

Además:

- Serví el frontend por **HTTPS**. Sin eso, la cámara del escáner no funciona en
  la mayoría de los navegadores.
- Configurá `RESPALDO_EXTERNO`. El sistema ya guarda una copia de la base en
  cada cierre de caja, pero esa copia vive en el mismo disco que la base y no
  sirve si ese disco se rompe. Con esto queda además un duplicado en una
  carpeta sincronizada o en un pendrive.
- **Probá una restauración antes de necesitarla.** Un respaldo que nadie probó
  restaurar no es un respaldo. Ver abajo.
- Mirá `backend/logs/` cuando algo falle: ahí quedan los errores del servidor.
  Antes salían por consola y se perdían.
- Para varias cajas en simultáneo conviene pasar a SQL Server o PostgreSQL
  cambiando `DATABASE_URL`.

### La red del local

Esto no aparece en ninguna lista de "cómo instalar un backend" porque no es un
problema del código: es un problema del comercio. Se descubre el día de la
instalación si no se piensa antes.

**IP fija en la PC que hace de servidor.** El resto de los equipos (otras
cajas, el celular del dueño, una tablet) le hablan por su IP en la red local
(`http://192.168.x.x`). Si el router le reparte una IP distinta cada vez que
se reinicia (lo normal con DHCP), esa dirección se corta el día menos pensado
y nadie sabe por qué "el sistema no anda" — en realidad el sistema está bien,
lo que cambió es a dónde hay que apuntar. Dos formas de resolverlo, de más a
menos prolija:

1. **Reserva DHCP en el router**: se le dice al router "a la MAC tal, dale
   siempre esta IP". El equipo se puede seguir reiniciando con DHCP normal.
2. **IP estática en Windows**: configurada a mano en las propiedades del
   adaptador de red. Más simple de explicar por teléfono, pero si el rango de
   la red cambia (un router nuevo) hay que tocarla de nuevo a mano.

Si un equipo dejó de conectarse después de tocar el router, el link *"¿No
podés entrar? Diagnóstico de conexión"* que aparece debajo del login muestra a
qué dirección le está intentando hablar ese equipo — suele alcanzar para
darse cuenta de que la IP vieja ya no es la de la PC servidor.

**Puerto abierto en el firewall de Windows.** Por default, el Firewall de
Windows bloquea las conexiones entrantes a un puerto que no esté
explícitamente permitido — incluso dentro de la misma red local. Sin esto, la
PC servidor se contesta a sí misma perfectamente (por eso "en esta máquina
funciona") y ningún otro equipo del local llega nunca. Hace falta una regla de
entrada para el puerto que use el servicio (ver
`installer/scripts/instalar-servicio.ps1`, por defecto 8000), en el perfil de
red **privada** — nunca en el perfil público, que expondría el POS a cualquier
red a la que se conecte esa PC.

**HTTPS y la cámara del celular.** El escáner por cámara (`useCamera.ts`)
funciona perfecto en desarrollo, pero los navegadores sólo prestan la cámara
en un "contexto seguro": HTTPS, o `localhost`. Un celular que entra por
`http://192.168.x.x` — que es como entra siempre en un comercio, salvo que se
arme HTTPS a propósito — no la va a poder usar, y el POS lo detecta y avisa en
vez de fallar en silencio.

Se decidió **no forzar HTTPS en esta versión** para no sumarle a la
instalación la complejidad de una autoridad certificadora propia (`mkcert`, un
certificado por equipo) sólo para poder escanear con la cámara de un celular.
La recomendación es la más simple: **en cualquier dispositivo que necesite
escanear, usar un lector de código de barras USB** (tipo *wedge*: escribe en
el campo como si fuera un teclado, no necesita driver ni configuración) en vez
de la cámara. Es además más rápido y confiable en el mostrador que apuntar con
el celular.

Si en algún momento hace falta escanear con la cámara de un celular sin cable
—por ejemplo, para reponer stock caminando por el depósito— existe el camino
de HTTPS con certificado propio que ya usa el entorno de desarrollo
(`pnpm dev:celular`, con el certificado de `scripts/generar-certificado.sh`):
llevarlo a producción implica instalar esa CA en cada equipo que vaya a usar
la cámara, lo cual es exactamente la complejidad operativa que se decidió
evitar por ahora.

---

## Seguridad

El sistema pasó por una auditoría con explotación real de cada hallazgo. Lo que
está implementado:

- **El precio sale siempre del catálogo del servidor.** Lo que manda el cliente
  es informativo: no se puede cobrar un producto de $2.000 a $1 editando el pedido.
- **Alta de usuarios sólo para administradores.** La única excepción es el
  primer usuario de una instalación vacía.
- **Freno a la fuerza bruta**: cinco intentos fallidos bloquean el login un minuto.
- **Ventas idempotentes**: reintentar la sincronización no duplica la venta.
- **Aislamiento por rol**: el cajero sólo ve sus propias ventas.
- **Verificación de importe en Mercado Pago**: no alcanza con que el pago figure
  aprobado, tiene que coincidir el monto.
- **Límites de tamaño** de petición y de líneas por venta.
- Cabeceras `X-Frame-Options`, `X-Content-Type-Options`, CSP, `Referrer-Policy`
  y HSTS en producción.
- Los PIN se guardan con **bcrypt**; las consultas usan el ORM, sin SQL armado a mano.

### Tests

Cubren los cálculos de plata (precio, impuesto en sus dos modos, descuentos,
devoluciones y arqueo de caja) y cada agujero de seguridad que se encontró en la
auditoría, para que no vuelvan a abrirse sin que nadie se entere. Corren contra
una base temporal: nunca tocan la del comercio.

```bash
cd backend
venv\Scripts\activate
pytest
```

Del lado del frontend, los tests cubren el flujo por teclado del POS de punta a
punta —el lector carga el producto, Enter encadena la venta, y la venta cobrada
queda guardada en el equipo aunque no haya servidor— más el saneo de los campos
de dinero y la lógica que decide qué hacer con una venta que el servidor
rechazó.

```bash
cd frontend
pnpm test
```

### Restaurar un respaldo

Se hace con el backend **detenido**: la base está en modo WAL y reemplazar el
archivo mientras alguien escribe deja un revoltijo.

```bash
cd backend
venv\Scripts\activate

python restaurar_respaldo.py                     # muestra las copias disponibles
python restaurar_respaldo.py applify_2026....db  # restaura esa
```

Antes de tocar nada verifica que la copia se abra, que tenga las tablas del
sistema y te dice cuántas ventas trae, para que compares con lo que esperabas.
La base que estaba en uso se guarda al lado con el sufijo `.reemplazada_<fecha>`,
así que si te equivocaste de copia todavía hay marcha atrás.

### Qué NO subir nunca al repositorio

- `backend/.env` — la clave de firma y el token de Mercado Pago
- `backend/applify.db` — las ventas y los PIN hasheados de los usuarios. Un PIN
  de 4 dígitos se rompe en segundos si alguien consigue el hash.
- `backend/respaldos/` — copias de la base, con los mismos datos adentro
- `backend/logs/` — errores del servidor, que pueden traer datos del local

Todo eso ya está en el `.gitignore`.

---

## Estructura

```
backend/
  app/
    main.py               Arranque, CORS, cabeceras y límite de tamaño
    config.py             Configuración y validaciones de arranque
    models.py             Tablas
    schemas.py            Validación de entrada y salida
    auth.py               Hash de PIN, tokens y anti fuerza bruta
    dependencies.py       Sesión actual y control de roles
    configuracion_defaults.py   Parámetros configurables
    routers/              auth, productos, categorias, proveedores, ventas,
                          devoluciones, stock, pedidos, cajas, reportes,
                          pagos, descuentos y configuracion
    respaldos.py          Copias de la base, locales y fuera del equipo
  alembic/versions/       Migraciones
  tests/                  Tests de los cálculos de plata y de seguridad
  logs/                   Errores del servidor (rotan solos)
  respaldos/              Copias de la base
  seed_admin.py           Crea el primer administrador

frontend/src/
  App.tsx                 Punto de venta
  Admin.tsx               Backoffice
  api.ts                  Cliente HTTP
  db.ts                   Base local (IndexedDB) para el modo sin conexión
  sincronizacion.ts       Qué hacer con una venta que el servidor rechazó
  tests/                  Tests del flujo por teclado del POS
  cajaLocal.ts            Turno de caja recordado en el equipo
  useConexion.ts          Detecta si el servidor responde de verdad
  components/             Configuración, toasts, gráficos y logo
```

---

## Stack

**Backend**: FastAPI · SQLAlchemy · Alembic · SQLite (o SQL Server) · bcrypt · PyJWT

**Frontend**: React 19 · TypeScript · Vite · Tailwind · Dexie (IndexedDB) ·
Recharts · Framer Motion · PWA · dependencias con pnpm

---

## Sobre las fechas

Las fechas se guardan en UTC, pero los reportes cuentan los días según el
**reloj de pared del local**. Son cosas distintas: en Argentina, a partir de
las 21:00 el día en UTC ya es el siguiente, así que comparar contra la fecha
guardada hacía que la recaudación del día apareciera en cero justo en el
horario de más venta.

Los reportes convierten el día local a un rango en UTC antes de consultar. Si
el sistema se usa en otro huso horario, funciona igual: toma la zona horaria de
la computadora donde corre el backend.

---

## Problemas comunes

**"El servidor no responde" en el POS**
Verificá que el backend esté levantado en el puerto 8001. Si acabás de bajar
cambios, reiniciá también el servidor de Vite: el proxy se define en `vite.config.ts`
y sólo se lee al arrancar.

**La cámara no abre**
Necesita HTTPS salvo en `localhost`. En equipos sin cámara el sistema lo detecta
y no muestra el pedido de permisos: se usa el lector USB o el ingreso manual.

**`alembic: command not found`**
Falta activar el entorno virtual (`venv\Scripts\activate`).
