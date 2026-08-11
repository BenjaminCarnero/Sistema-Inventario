from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models, schemas, database, dependencies, respaldos

router = APIRouter(prefix="/respaldos", tags=["respaldos"])

# Una copia de la base contiene las ventas y los PIN hasheados de todos los
# usuarios. Es el archivo más sensible del sistema: sólo el administrador.
solo_admin = dependencies.require_role([models.RolEnum.ADMIN.value])


@router.get("/", response_model=List[schemas.Respaldo])
def listar_respaldos(
    current_user: models.Usuario = Depends(solo_admin),
):
    return [schemas.Respaldo(**r) for r in respaldos.listar()]


@router.post("/", response_model=schemas.Respaldo, status_code=status.HTTP_201_CREATED)
def crear_respaldo(
    db: Session = Depends(database.get_db),
    current_user: models.Usuario = Depends(solo_admin),
):
    ruta = respaldos.crear("manual")
    if ruta is None:
        raise HTTPException(
            status_code=400,
            detail="La base no es un archivo SQLite: las copias las maneja el motor de base de datos.",
        )

    info = ruta.stat()
    return schemas.Respaldo(
        nombre=ruta.name,
        bytes=info.st_size,
        fecha_hora=datetime.fromtimestamp(info.st_mtime),
    )


@router.get("/{nombre}")
def descargar_respaldo(
    nombre: str,
    current_user: models.Usuario = Depends(solo_admin),
):
    """Descarga una copia para sacarla de la computadora.

    Una copia que vive en el mismo disco que la base no protege del caso más
    común, que es que ese disco se rompa.
    """
    ruta = respaldos.ruta_de(nombre)
    if ruta is None:
        raise HTTPException(status_code=404, detail="Copia no encontrada")

    return FileResponse(
        path=str(ruta),
        media_type="application/octet-stream",
        filename=ruta.name,
    )
