from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas, database, dependencies

router = APIRouter(prefix="/proveedores", tags=["proveedores"])

gestor_proveedores = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)


def _limpiar(proveedor: schemas.ProveedorCreate) -> dict:
    datos = proveedor.model_dump()
    datos["nombre"] = (datos.get("nombre") or "").strip()
    if not datos["nombre"]:
        raise HTTPException(status_code=400, detail="El nombre del proveedor no puede estar vacío")

    for campo in ("telefono", "email", "cuit", "notas"):
        valor = (datos.get(campo) or "").strip()
        datos[campo] = valor or None

    # El teléfono se usa para armar un enlace de WhatsApp, así que se guarda
    # sólo con dígitos y un + opcional adelante. Los guiones y paréntesis que
    # uno escribe naturalmente romperían el enlace.
    if datos["telefono"]:
        limpio = "".join(c for c in datos["telefono"] if c.isdigit() or c == "+")
        if len(limpio.lstrip("+")) < 6:
            raise HTTPException(status_code=400, detail="El teléfono no parece válido")
        datos["telefono"] = limpio

    return datos


@router.get("/", response_model=List[schemas.Proveedor])
def listar_proveedores(
    incluir_inactivos: bool = Query(False),
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_proveedores),
):
    query = db.query(models.Proveedor)
    if not incluir_inactivos:
        query = query.filter(models.Proveedor.activo == True)  # noqa: E712
    return query.order_by(models.Proveedor.nombre).all()


@router.post("/", response_model=schemas.Proveedor, status_code=status.HTTP_201_CREATED)
def crear_proveedor(
    proveedor: schemas.ProveedorCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_proveedores),
):
    datos = _limpiar(proveedor)

    if db.query(models.Proveedor).filter(models.Proveedor.nombre == datos["nombre"]).first():
        raise HTTPException(status_code=400, detail="Ya existe un proveedor con ese nombre")

    nuevo = models.Proveedor(**datos)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.put("/{proveedor_id}", response_model=schemas.Proveedor)
def actualizar_proveedor(
    proveedor_id: int,
    proveedor: schemas.ProveedorCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_proveedores),
):
    db_proveedor = db.query(models.Proveedor).filter(models.Proveedor.id == proveedor_id).first()
    if not db_proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    datos = _limpiar(proveedor)

    repetido = db.query(models.Proveedor).filter(
        models.Proveedor.nombre == datos["nombre"],
        models.Proveedor.id != proveedor_id,
    ).first()
    if repetido:
        raise HTTPException(status_code=400, detail="Ya existe otro proveedor con ese nombre")

    for clave, valor in datos.items():
        setattr(db_proveedor, clave, valor)

    db.commit()
    db.refresh(db_proveedor)
    return db_proveedor


@router.delete("/{proveedor_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_proveedor(
    proveedor_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_proveedores),
):
    """Da de baja al proveedor. Si tiene historial no se borra, se desactiva.

    Los pedidos viejos tienen que seguir diciendo a quién se le compró, así que
    borrarlo de verdad sólo es posible mientras no haya dejado rastro.
    """
    db_proveedor = db.query(models.Proveedor).filter(models.Proveedor.id == proveedor_id).first()
    if not db_proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    tiene_pedidos = db.query(models.Pedido).filter(
        models.Pedido.proveedor_id == proveedor_id
    ).first() is not None

    # Los productos quedan sin proveedor en cualquiera de los dos casos
    db.query(models.Producto).filter(
        models.Producto.proveedor_id == proveedor_id
    ).update({models.Producto.proveedor_id: None})

    if tiene_pedidos:
        db_proveedor.activo = False
    else:
        db.delete(db_proveedor)

    db.commit()
