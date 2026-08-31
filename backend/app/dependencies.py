from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session
from app import models, schemas, database
from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Variante que no falla si no viene token: la usa el alta de usuarios, que
# necesita distinguir "sistema sin inicializar" de "hace falta ser admin".
oauth2_scheme_opcional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sujeto = payload.get("sub")
        if sujeto is None:
            raise credentials_exception
        # El `sub` de un token viejo es el nombre del usuario, no el id. Esos
        # tokens no se aceptan: son justamente los que abrían la puerta a la
        # escalada por renombrado. Al desplegar esto, las sesiones abiertas se
        # cierran una vez y hay que volver a entrar.
        token_data = schemas.TokenData(
            usuario_id=int(sujeto),
            rol=payload.get("rol"),
            credenciales_version=payload.get("cv"),
        )
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise credentials_exception

    user = db.query(models.Usuario).filter(models.Usuario.id == token_data.usuario_id).first()
    if user is None:
        raise credentials_exception

    # Cambiar o reiniciar el PIN incrementa la versión, así que un token
    # emitido antes deja de servir en el acto. Sin esto, sacar de circulación
    # un PIN visto por encima del hombro no cerraba nada: la sesión abierta
    # seguía valiendo hasta doce horas más.
    if (token_data.credenciales_version or 0) != (user.credenciales_version or 1):
        raise credentials_exception

    return user


def get_current_active_user(current_user: models.Usuario = Depends(get_current_user)):
    # Dar de baja a un usuario corta sus sesiones abiertas al instante,
    # porque el estado se lee de la base y no del token.
    if not current_user.estado:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_role(roles: list[int]):
    """El rol se toma de la base, no del token: un cambio de permisos se
    aplica de inmediato aunque el usuario tenga una sesión abierta."""
    def role_checker(current_user: models.Usuario = Depends(get_current_active_user)):
        if current_user.rol_id not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges")
        return current_user
    return role_checker
