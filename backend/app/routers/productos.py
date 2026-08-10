from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas, database, dependencies

router = APIRouter(prefix="/productos", tags=["productos"])


def _validar_producto(datos: dict, db: Session = None):
    """Chequeos de negocio y de seguridad comunes al alta y la edición."""
    # SQLite no fuerza las claves foráneas por defecto: sin este chequeo, un
    # producto podía quedar apuntando a una categoría que no existe.
    categoria_id = datos.get("categoria_id")
    if categoria_id is not None and db is not None:
        existe = db.query(models.Categoria).filter(models.Categoria.id == categoria_id).first()
        if not existe:
            raise HTTPException(status_code=400, detail="La categoría indicada no existe")

    imagen = datos.get("imagen_url")
    if imagen:
        imagen = str(imagen).strip()
        # Sólo http(s) o imagen embebida: evita esquemas raros guardados en la
        # base y reutilizados después en otros contextos.
        if not (imagen.startswith("http://") or imagen.startswith("https://") or imagen.startswith("data:image/")):
            raise HTTPException(
                status_code=400,
                detail="La imagen debe ser una URL http(s) o una imagen embebida (data:image/...)",
            )
        if len(imagen) > 400_000:
            raise HTTPException(status_code=400, detail="La imagen del producto es demasiado grande")

    for campo, etiqueta in (("precio_venta", "El precio de venta"), ("costo", "El costo")):
        valor = datos.get(campo)
        if valor is not None:
            if valor < 0:
                raise HTTPException(status_code=400, detail=f"{etiqueta} no puede ser negativo")
            if valor > 1_000_000_000:
                raise HTTPException(status_code=400, detail=f"{etiqueta} es demasiado alto")

    codigo = datos.get("codigo_barras")
    if codigo is not None and not str(codigo).strip():
        raise HTTPException(status_code=400, detail="El código de barras no puede estar vacío")

    nombre = datos.get("nombre")
    if nombre is not None and not str(nombre).strip():
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")


@router.get("/", response_model=List[schemas.Producto])
def read_productos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    return db.query(models.Producto).offset(skip).limit(limit).all()


@router.post("/", response_model=schemas.Producto, status_code=status.HTTP_201_CREATED)
def create_producto(
    producto: schemas.ProductoCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        dependencies.require_role([models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value])
    ),
):
    _validar_producto(producto.model_dump(), db)

    db_producto = db.query(models.Producto).filter(
        models.Producto.codigo_barras == producto.codigo_barras
    ).first()
    if db_producto:
        raise HTTPException(status_code=400, detail="Ya existe un producto con ese código de barras")

    new_producto = models.Producto(**producto.model_dump())
    db.add(new_producto)
    db.commit()
    db.refresh(new_producto)
    return new_producto


@router.put("/{producto_id}", response_model=schemas.Producto)
def update_producto(
    producto_id: int,
    producto_update: schemas.ProductoUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(
        dependencies.require_role([models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value])
    ),
):
    db_producto = db.query(models.Producto).filter(models.Producto.id == producto_id).first()
    if not db_producto:
        raise HTTPException(status_code=404, detail="Producto not found")

    update_data = producto_update.model_dump(exclude_unset=True)
    _validar_producto(update_data, db)

    # Cambiar el código de barras no puede pisar el de otro producto
    nuevo_codigo = update_data.get("codigo_barras")
    if nuevo_codigo and nuevo_codigo != db_producto.codigo_barras:
        repetido = db.query(models.Producto).filter(
            models.Producto.codigo_barras == nuevo_codigo,
            models.Producto.id != producto_id,
        ).first()
        if repetido:
            raise HTTPException(status_code=400, detail="Ya existe otro producto con ese código de barras")

    for key, value in update_data.items():
        setattr(db_producto, key, value)

    db.commit()
    db.refresh(db_producto)
    return db_producto
