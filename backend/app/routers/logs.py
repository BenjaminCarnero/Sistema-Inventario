from datetime import datetime

from fastapi import APIRouter, Depends, Response

from app import models, dependencies, logs

router = APIRouter(prefix="/logs", tags=["logs"])

# Los logs pueden tener direcciones IP y nombres de usuario en los mensajes de
# error: no es información para un cajero.
solo_admin = dependencies.require_role([models.RolEnum.ADMIN.value])


@router.get("/descargar")
def descargar_logs(current_user: models.Usuario = Depends(solo_admin)):
    contenido = logs.zip_de_logs()
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        content=contenido,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="logs_{marca}.zip"'},
    )
