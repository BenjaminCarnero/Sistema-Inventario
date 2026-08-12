"""Crea el primer usuario administrador de una instalación nueva.

Se ejecuta una sola vez, después de aplicar las migraciones:

    python seed_admin.py

Pide el PIN por teclado en vez de dejarlo escrito en el código, para que no
quede una credencial por defecto que todo el mundo conozca.
"""
import getpass
import sys

from sqlalchemy.orm import Session

from app import auth, models
from app.database import SessionLocal

# El mínimo sale de la misma política que aplica la API. Estaba fijo en 4 acá,
# así que el primer administrador —la cuenta más privilegiada del sistema, y la
# única que existe en toda instalación nueva— era también la única que podía
# saltarse el mínimo de 8 que se les exige a los demás.
PIN_MINIMO = auth.pin_minimo(models.RolEnum.ADMIN.value)


def crear_admin():
    db: Session = SessionLocal()
    try:
        if db.query(models.Usuario).first() is not None:
            print("Ya hay usuarios cargados. Si necesitás otro administrador, "
                  "crealo desde el panel con una cuenta de admin.")
            return

        nombre = input("Nombre del administrador [admin]: ").strip() or "admin"

        pin = getpass.getpass(f"PIN de acceso (mínimo {PIN_MINIMO} caracteres): ")
        if len(pin) < PIN_MINIMO:
            print(f"El PIN debe tener al menos {PIN_MINIMO} caracteres.", file=sys.stderr)
            sys.exit(1)

        if pin != getpass.getpass("Repetí el PIN: "):
            print("Los PIN no coinciden.", file=sys.stderr)
            sys.exit(1)

        db.add(models.Usuario(
            nombre=nombre,
            pin_acceso=auth.get_password_hash(pin),
            rol_id=models.RolEnum.ADMIN.value,
            estado=True,
        ))
        db.commit()
        print(f"\nListo. Entrá al sistema con el usuario '{nombre}'.")
    finally:
        db.close()


if __name__ == "__main__":
    crear_admin()
