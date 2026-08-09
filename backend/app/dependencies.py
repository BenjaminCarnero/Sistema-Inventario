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
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username, rol=payload.get("rol"))
    except jwt.InvalidTokenError:
        raise credentials_exception

    user = db.query(models.Usuario).filter(models.Usuario.nombre == token_data.username).first()
    if user is None:
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
