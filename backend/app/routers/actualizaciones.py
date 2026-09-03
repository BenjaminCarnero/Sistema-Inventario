from fastapi import APIRouter, Depends

from app import models, dependencies, actualizaciones

router = APIRouter(prefix="/actualizaciones", tags=["actualizaciones"])

# Es información operativa (qué versión corre, si hay una más nueva), no algo
# que necesite ver un cajero: sólo el administrador.
solo_admin = dependencies.require_role([models.RolEnum.ADMIN.value])


@router.get("/disponible")
def hay_actualizacion_disponible(current_user: models.Usuario = Depends(solo_admin)):
    return actualizaciones.buscar_disponible()
