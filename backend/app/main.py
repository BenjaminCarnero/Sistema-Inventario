import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from app import red
from app.config import BASE_DIR, settings, es_produccion, VERSION

# --- Registro de errores ---------------------------------------------------
# Sin esto los errores salen por la consola y ahí mueren: en una PC de
# mostrador, con el backend minimizado o corriendo como servicio, no los ve
# nadie. Cuando el cajero dice "me tiró error", esto es lo único que queda.
#
# Rota a los 2 MB y guarda 5 archivos: alcanza para varias semanas de un
# comercio y no llena el disco solo. Nunca se escriben PIN ni tokens.
CARPETA_LOGS = BASE_DIR / "logs"
CARPETA_LOGS.mkdir(parents=True, exist_ok=True)

_archivo = RotatingFileHandler(
    CARPETA_LOGS / "backend.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8",
)
_archivo.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s: %(message)s"
))

_raiz = logging.getLogger()
_raiz.setLevel(logging.INFO)
_raiz.addHandler(_archivo)
# Los errores de uvicorn también van al archivo, que es donde se busca después
for _nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_nombre).addHandler(_archivo)

# En producción no se publica la documentación interactiva: le da a un atacante
# el mapa completo de la API (rutas, parámetros y esquemas) sin esfuerzo.
app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url=None if es_produccion else "/docs",
    redoc_url=None if es_produccion else "/redoc",
    openapi_url=None if es_produccion else "/openapi.json",
)

# Tamaño máximo de una petición. Sin esto, un pedido de varios MB deja al
# servidor procesando y la caja deja de responder.
MAX_BODY_BYTES = 1_000_000  # 1 MB


@app.middleware("http")
async def limitar_tamano_body(request: Request, call_next):
    largo = request.headers.get("content-length")
    if largo:
        try:
            if int(largo) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "La petición es demasiado grande"},
                )
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Content-Length inválido"},
            )
    return await call_next(request)


# Prefijos que atiende la API. Todo lo demás lo sirve el frontend, y necesita
# una CSP distinta: la de la API prohíbe cargar absolutamente todo, que es
# correcto para JSON y deja la pantalla en blanco para una aplicación web.
PREFIJOS_API = (
    "/auth", "/productos", "/ventas", "/cajas", "/reportes", "/pagos",
    "/descuentos", "/configuracion", "/devoluciones", "/stock", "/categorias",
    "/proveedores", "/pedidos", "/auditoria", "/respaldos", "/actualizaciones",
    "/health", "/docs", "/redoc", "/openapi.json",
)

# La API no carga nada: ni scripts, ni imágenes, ni hojas de estilo.
CSP_API = "default-src 'none'; frame-ancestors 'none'"

# El frontend sí, pero sólo lo suyo y de su mismo origen.
#   - `data:` en img-src porque el logo del comercio puede ser una imagen
#     embebida, y `https:` porque también puede ser una URL.
#   - `'unsafe-inline'` en style-src porque las animaciones escriben estilos
#     en el atributo `style` de cada elemento.
#   - `connect-src 'self'` alcanza: la API se sirve desde el mismo origen.
CSP_FRONTEND = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self'; "
    "manifest-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def es_ruta_de_api(camino: str) -> bool:
    """¿Este camino lo atiende la API, o es del frontend?

    Se compara por segmento y no con un `startswith` pelado: `/ventasfalsas`
    empieza con `/ventas` y no es una ruta de la API.
    """
    for prefijo in PREFIJOS_API:
        if camino == prefijo or camino.startswith(prefijo + "/"):
            return True
    return False


# --- Freno general de peticiones -------------------------------------------
# El login tiene su propio freno, más estricto y guardado en la base. Este es
# el techo para todo lo demás: sin él, cualquiera con la URL —y publicado en
# internet la URL la tiene cualquiera— puede martillar la API hasta que la caja
# deje de responder. Un cliente con un bucle roto hace lo mismo sin mala fe.
#
# Se lleva en memoria a propósito, al revés que el freno del login. Ahí importa
# que sobreviva al reinicio porque cuenta intentos de adivinar un PIN; acá sólo
# se está recortando un pico de tráfico, y perder la cuenta al reiniciar no
# tiene consecuencias.
_VENTANA_SEGUNDOS = 60
_peticiones_por_ip: dict[str, list[float]] = {}


@app.middleware("http")
async def limitar_peticiones(request: Request, call_next):
    techo = settings.LIMITE_PETICIONES_POR_MINUTO
    if techo <= 0:
        return await call_next(request)

    # El POS consulta /health cada 15 segundos para saber si hay servidor. Es
    # lo que sostiene el aviso de "sin conexión": frenarlo sería apagar el
    # sensor justo cuando hay problemas.
    if request.url.path == "/health":
        return await call_next(request)

    ahora = time.monotonic()
    ip = red.ip_del_cliente(request)

    marcas = [t for t in _peticiones_por_ip.get(ip, []) if ahora - t < _VENTANA_SEGUNDOS]

    if len(marcas) >= techo:
        _peticiones_por_ip[ip] = marcas
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Demasiadas peticiones. Esperá un momento."},
            headers={"Retry-After": str(_VENTANA_SEGUNDOS)},
        )

    marcas.append(ahora)
    _peticiones_por_ip[ip] = marcas

    # Limpieza oportunista: sin esto el diccionario guarda una entrada por cada
    # IP que haya pasado alguna vez, y en un servidor publicado eso no para.
    if len(_peticiones_por_ip) > 2048:
        for otra_ip in [k for k, v in _peticiones_por_ip.items()
                        if not v or ahora - v[-1] > _VENTANA_SEGUNDOS]:
            _peticiones_por_ip.pop(otra_ip, None)

    return await call_next(request)


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    # Evita que la app se embeba en un iframe ajeno (clickjacking)
    respuesta.headers["X-Frame-Options"] = "DENY"
    # Impide que el navegador adivine el tipo de contenido
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    es_api = es_ruta_de_api(request.url.path)
    respuesta.headers["Content-Security-Policy"] = CSP_API if es_api else CSP_FRONTEND
    respuesta.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    if es_produccion:
        # Sólo en producción: en local no hay HTTPS y rompería el acceso
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return respuesta


# allow_credentials sólo tiene sentido con una lista concreta de orígenes: la
# combinación "*" + credenciales la rechaza el propio navegador y además haría
# que cualquier sitio pudiera llamar a la API en nombre del usuario.
_origenes_abiertos = "*" in settings.CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=not _origenes_abiertos,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME, "version": VERSION}


from app.routers import (
    auth, productos, ventas, cajas, reportes, pagos, descuentos,
    configuracion, devoluciones, stock, categorias, proveedores, pedidos,
    auditoria, respaldos, actualizaciones,
)
app.include_router(auth.router)
app.include_router(productos.router)
app.include_router(ventas.router)
app.include_router(cajas.router)
app.include_router(reportes.router)
app.include_router(pagos.router)
app.include_router(descuentos.router)
app.include_router(configuracion.router)
app.include_router(devoluciones.router)
app.include_router(stock.router)
app.include_router(categorias.router)
app.include_router(proveedores.router)
app.include_router(pedidos.router)
app.include_router(auditoria.router)
app.include_router(respaldos.router)
app.include_router(actualizaciones.router)


# --- Frontend ---------------------------------------------------------------
# Si al lado hay un frontend compilado, lo sirve esta misma aplicación. Así un
# comercio es un solo contenedor y un solo puerto, en vez de dos servicios que
# hay que mantener sincronizados.
#
# Va al final a propósito: las rutas de la API se registran antes y ganan.
CARPETA_FRONTEND = Path(settings.FRONTEND_DIST or (BASE_DIR.parent / "frontend" / "dist"))


def _parece_navegacion(request: Request) -> bool:
    """¿Es alguien escribiendo una dirección, o el navegador pidiendo un asset?

    Sólo la primera merece que se le devuelva el index: es la que después
    resuelve la ruta del lado del cliente. Se mira `Accept`, que en una
    navegación trae `text/html` y en un `fetch` o en la carga de un script no.
    """
    return "text/html" in request.headers.get("accept", "")

if (CARPETA_FRONTEND / "index.html").is_file():
    _INDEX = CARPETA_FRONTEND / "index.html"
    _RAIZ = CARPETA_FRONTEND.resolve()

    @app.get("/{ruta:path}", include_in_schema=False)
    def servir_frontend(request: Request, ruta: str):
        """Sirve el archivo pedido, o el index para las rutas de la aplicación.

        El POS usa rutas del lado del cliente (`/admin`), así que entrar
        directo por la barra de direcciones tiene que devolver el index y no un
        404. Lo que sí existe como archivo se devuelve tal cual.
        """
        # Lo que cae acá empezando con un prefijo de la API es una ruta de API
        # que no existe, y tiene que decirlo. Devolver el index con 200 hacía
        # que `GET /ventas/cualquier-cosa` contestara HTML: la API entera se
        # quedó sin 404, el cliente necesitó una función para adivinar cuándo
        # "el backend no conoce esta ruta", y cualquier monitoreo que busque
        # sondeos por sus 404 quedó ciego.
        if es_ruta_de_api("/" + ruta):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": "Esa ruta de la API no existe"},
            )

        if ruta:
            archivo = (CARPETA_FRONTEND / ruta).resolve()
            # El nombre llega desde la red: sin este chequeo, "../../.env"
            # serviría para sacar cualquier archivo del servidor.
            if _RAIZ in archivo.parents and archivo.is_file():
                return FileResponse(archivo)

            # Un archivo que no existe se contesta 404, no con el index. El
            # index sólo tiene sentido para una ruta de navegación: pedir un
            # .js o un .png que no está y recibir HTML con 200 esconde el
            # error justo donde hay que verlo.
            if not _parece_navegacion(request):
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"detail": "No encontrado"},
                )

        return FileResponse(_INDEX)
else:
    logging.getLogger(__name__).info(
        "No hay frontend compilado en %s: se sirve sólo la API.", CARPETA_FRONTEND
    )
