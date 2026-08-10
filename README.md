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
npm install
npm run dev
```

Abrí `http://localhost:5173`. El punto de venta está en `/` y el backoffice en
`/admin`.

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

La forma más simple de tener HTTPS con un certificado válido, sin comprar un
dominio ni abrir puertos en el router, es [Tailscale](https://tailscale.com):
arma una red privada entre tus dispositivos y emite el certificado solo.

Una sola vez, en la cuenta:

1. Habilitar **Serve** y **HTTPS Certificates** en la consola de administración
   (`login.tailscale.com`, sección DNS).
2. Instalar Tailscale en la computadora y en el celular, con la misma cuenta.

Después, con `npm run dev` corriendo:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:5173
```

`tailscale serve status` muestra la dirección `https://…​.ts.net` que queda
publicada. Esa se abre desde el celular.

Con eso el navegador considera el sitio seguro: **anda el escáner por cámara** y
se puede instalar como aplicación desde el navegador.

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

Mercado Pago no aparece mientras no haya conexión, porque necesita el servidor.

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
```

Con `ENTORNO=produccion` el arranque **falla** si falta la `SECRET_KEY` o si
`CORS_ORIGINS` está en `"*"`, se oculta la documentación de la API y se activa
HSTS.

Además:

- Serví el frontend por **HTTPS**. Sin eso, la cámara del escáner no funciona en
  la mayoría de los navegadores.
- Hacé **copias de la base** (`backend/applify.db`). Es un archivo: copiarlo
  alcanza.
- Para varias cajas en simultáneo conviene pasar a SQL Server o PostgreSQL
  cambiando `DATABASE_URL`.

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

### Qué NO subir nunca al repositorio

- `backend/.env` — la clave de firma y el token de Mercado Pago
- `backend/applify.db` — las ventas y los PIN hasheados de los usuarios. Un PIN
  de 4 dígitos se rompe en segundos si alguien consigue el hash.

Las dos cosas ya están en el `.gitignore`.

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
  alembic/versions/       Migraciones
  tests/                  Tests de los cálculos de plata y de seguridad
  seed_admin.py           Crea el primer administrador

frontend/src/
  App.tsx                 Punto de venta
  Admin.tsx               Backoffice
  api.ts                  Cliente HTTP
  db.ts                   Base local (IndexedDB) para el modo sin conexión
  cajaLocal.ts            Turno de caja recordado en el equipo
  useConexion.ts          Detecta si el servidor responde de verdad
  components/             Configuración, toasts, gráficos y logo
```

---

## Stack

**Backend**: FastAPI · SQLAlchemy · Alembic · SQLite (o SQL Server) · bcrypt · PyJWT

**Frontend**: React 19 · TypeScript · Vite · Tailwind · Dexie (IndexedDB) ·
Recharts · Framer Motion · PWA

---

## Problemas comunes

**"El servidor no responde" en el POS**
Verificá que el backend esté levantado en el puerto 8001. Si acabás de bajar
cambios, reiniciá también `npm run dev`: el proxy se define en `vite.config.ts`
y sólo se lee al arrancar.

**La cámara no abre**
Necesita HTTPS salvo en `localhost`. En equipos sin cámara el sistema lo detecta
y no muestra el pedido de permisos: se usa el lector USB o el ingreso manual.

**`alembic: command not found`**
Falta activar el entorno virtual (`venv\Scripts\activate`).
