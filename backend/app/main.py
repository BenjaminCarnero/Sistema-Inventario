import logging
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import BASE_DIR, settings, es_produccion

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


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    # Evita que la app se embeba en un iframe ajeno (clickjacking)
    respuesta.headers["X-Frame-Options"] = "DENY"
    # Impide que el navegador adivine el tipo de contenido
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    # La API sólo devuelve JSON: no necesita cargar nada
    respuesta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
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
    return {"status": "ok", "project": settings.PROJECT_NAME}


from app.routers import (
    auth, productos, ventas, cajas, reportes, pagos, descuentos,
    configuracion, devoluciones, stock, categorias, proveedores, pedidos,
    auditoria, respaldos,
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
