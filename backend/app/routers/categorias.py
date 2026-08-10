from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas, database, dependencies

router = APIRouter(prefix="/categorias", tags=["categorias"])

gestor_categorias = dependencies.require_role(
    [models.RolEnum.ADMIN.value, models.RolEnum.ENCARGADO.value]
)


@router.get("/", response_model=List[schemas.Categoria])
def listar_categorias(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(dependencies.get_current_active_user),
):
    """La lee cualquier usuario: el POS la usa para filtrar el catálogo."""
    return db.query(models.Categoria).order_by(models.Categoria.nombre).all()


@router.post("/", response_model=schemas.Categoria, status_code=status.HTTP_201_CREATED)
def crear_categoria(
    categoria: schemas.CategoriaCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_categorias),
):
    nombre = (categoria.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    if db.query(models.Categoria).filter(models.Categoria.nombre == nombre).first():
        raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre")

    nueva = models.Categoria(nombre=nombre)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.put("/{categoria_id}", response_model=schemas.Categoria)
def actualizar_categoria(
    categoria_id: int,
    categoria: schemas.CategoriaCreate,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_categorias),
):
    db_categoria = db.query(models.Categoria).filter(models.Categoria.id == categoria_id).first()
    if not db_categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    nombre = (categoria.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    repetida = db.query(models.Categoria).filter(
        models.Categoria.nombre == nombre,
        models.Categoria.id != categoria_id,
    ).first()
    if repetida:
        raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre")

    db_categoria.nombre = nombre
    db.commit()
    db.refresh(db_categoria)
    return db_categoria


@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_categoria(
    categoria_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(gestor_categorias),
):
    db_categoria = db.query(models.Categoria).filter(models.Categoria.id == categoria_id).first()
    if not db_categoria:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    # Los productos no se borran: quedan sin categoría
    db.query(models.Producto).filter(
        models.Producto.categoria_id == categoria_id
    ).update({models.Producto.categoria_id: None})

    db.delete(db_categoria)
    db.commit()
