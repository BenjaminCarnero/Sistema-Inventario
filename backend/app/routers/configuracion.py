import re
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models, database, dependencies, auditoria


def _resumir(valor: str, maximo: int = 120) -> str:
    """Acorta los valores largos para que la auditoría siga siendo legible."""
    if valor is None:
        return None
    if len(valor) <= maximo:
        return valor
    return f"{valor[:maximo]}… ({len(valor)} caracteres)"
from app.configuracion_defaults import DEFAULTS, CATEGORIAS, castear, serializar

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

# Sólo el admin puede cambiar la configuración; leerla lo puede hacer
# cualquier usuario logueado porque el POS necesita el IVA y la moneda.
solo_admin = dependencies.require_role([models.RolEnum.ADMIN.value])

HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class ParametroOut(BaseModel):
    clave: str
    valor: Any
    tipo: str
    categoria: str
    descripcion: str | None = None


class ConfiguracionUpdate(BaseModel):
    valores: Dict[str, Any]


def obtener_config(db: Session) -> Dict[str, Any]:
    """Devuelve la configuración efectiva: lo guardado en la base, completado
    con los valores por defecto para las claves que todavía no se tocaron."""
    guardados = {c.clave: c for c in db.query(models.Configuracion).all()}

    efectiva: Dict[str, Any] = {}
    for clave, meta in DEFAULTS.items():
        fila = guardados.get(clave)
        if fila is not None:
            efectiva[clave] = castear(fila.valor, fila.tipo)
        else:
            efectiva[clave] = castear(meta["valor"], meta["tipo"])
    return efectiva


@router.get("/", response_model=List[ParametroOut])
def leer_configuracion(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    guardados = {c.clave: c for c in db.query(models.Configuracion).all()}

    parametros = []
    for clave, meta in DEFAULTS.items():
        fila = guardados.get(clave)
        valor_texto = fila.valor if fila is not None else meta["valor"]
        parametros.append(ParametroOut(
            clave=clave,
            valor=castear(valor_texto, meta["tipo"]),
            tipo=meta["tipo"],
            categoria=meta["categoria"],
            descripcion=meta["descripcion"],
        ))
    return parametros


# Lo que hace falta para pintar la pantalla de acceso. No son secretos: son el
# nombre, el logo y los colores que el comercio muestra en su vidriera. El
# resto de la configuración (impuestos, topes, métodos de pago) sigue pidiendo
# sesión.
CLAVES_DE_MARCA = ("negocio_nombre", "marca_logo_url", "marca_color_primario", "marca_color_acento")


@router.get("/marca")
def leer_marca(db: Session = Depends(database.get_db)):
    """Marca del comercio, sin necesidad de haber entrado.

    Sin esto, un dispositivo que nunca inició sesión muestra el nombre y los
    colores por defecto justo en la primera pantalla que se ve.
    """
    config = obtener_config(db)
    return {clave: config.get(clave) for clave in CLAVES_DE_MARCA}


@router.get("/categorias")
def leer_categorias(current_user: models.Usuario = Depends(dependencies.get_current_active_user)):
    return CATEGORIAS


def _validar(clave: str, valor: Any):
    if clave in ("marca_color_primario", "marca_color_acento"):
        if not HEX_COLOR.match(str(valor).strip()):
            raise HTTPException(
                status_code=400,
                detail=f"'{valor}' no es un color hexadecimal válido (ej: #8251EE)"
            )

    if clave == "marca_logo_url":
        url = str(valor).strip()
        # Se permite vacío (usa el logo por defecto), una URL http(s) o un data URI
        if url and not (url.startswith("http://") or url.startswith("https://") or url.startswith("data:image/")):
            raise HTTPException(
                status_code=400,
                detail="El logo debe ser una URL http(s) o una imagen embebida (data:image/...)"
            )
        # El logo embebido viaja en cada lectura de configuración, así que se
        # limita para no inflar la respuesta. El frontend lo reduce antes de enviar.
        if len(url) > 400_000:
            raise HTTPException(
                status_code=400,
                detail="La imagen del logo es demasiado grande. Usá una más chica o pegá una URL."
            )

    if clave == "app_nombre" and not str(valor).strip():
        raise HTTPException(status_code=400, detail="El nombre de la aplicación no puede quedar vacío")

    if clave == "iva_porcentaje":
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="El IVA debe ser un número")
        if numero < 0 or numero > 100:
            raise HTTPException(status_code=400, detail="El IVA debe estar entre 0 y 100")

    if clave == "monto_maximo_efectivo":
        try:
            tope = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="El tope de efectivo debe ser un número")
        if tope <= 0:
            raise HTTPException(status_code=400, detail="El tope de efectivo tiene que ser mayor a 0")
        if tope > 1_000_000_000:
            raise HTTPException(status_code=400, detail="El tope de efectivo es demasiado alto")

    if clave == "umbral_stock_bajo":
        try:
            if int(float(valor)) < 0:
                raise HTTPException(status_code=400, detail="El umbral de stock no puede ser negativo")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="El umbral de stock debe ser un número")

    if clave == "metodos_pago_habilitados":
        if not isinstance(valor, list) or not valor:
            raise HTTPException(status_code=400, detail="Tiene que haber al menos un método de pago habilitado")

    if clave == "moneda_simbolo" and not str(valor).strip():
        raise HTTPException(status_code=400, detail="El símbolo de moneda no puede quedar vacío")

    if clave == "negocio_nombre" and not str(valor).strip():
        raise HTTPException(status_code=400, detail="El nombre del negocio no puede quedar vacío")


@router.put("/", response_model=List[ParametroOut])
def actualizar_configuracion(
    payload: ConfiguracionUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(solo_admin),
):
    desconocidas = set(payload.valores) - set(DEFAULTS)
    if desconocidas:
        raise HTTPException(status_code=400, detail=f"Parámetros desconocidos: {', '.join(sorted(desconocidas))}")

    for clave, valor in payload.valores.items():
        _validar(clave, valor)

    for clave, valor in payload.valores.items():
        meta = DEFAULTS[clave]
        texto = serializar(valor, meta["tipo"])

        fila = db.query(models.Configuracion).filter(models.Configuracion.clave == clave).first()
        anterior = fila.valor if fila is not None else meta["valor"]

        if fila is None:
            fila = models.Configuracion(
                clave=clave,
                valor=texto,
                tipo=meta["tipo"],
                categoria=meta["categoria"],
                descripcion=meta["descripcion"],
            )
            db.add(fila)
        else:
            fila.valor = texto

        # El logo puede ser una imagen embebida de cientos de miles de
        # caracteres: guardar eso en la auditoría la volvería inservible.
        if anterior != texto:
            auditoria.registrar(
                db, current_user, "configuracion", "MODIFICAR",
                entidad_nombre=clave, campo=clave,
                valor_anterior=_resumir(anterior), valor_nuevo=_resumir(texto),
            )

    db.commit()
    return leer_configuracion(db=db, current_user=current_user)


@router.post("/restaurar", response_model=List[ParametroOut])
def restaurar_defaults(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(solo_admin),
):
    """Borra las personalizaciones y vuelve a los valores de fábrica."""
    db.query(models.Configuracion).delete()
    db.commit()
    return leer_configuracion(db=db, current_user=current_user)
