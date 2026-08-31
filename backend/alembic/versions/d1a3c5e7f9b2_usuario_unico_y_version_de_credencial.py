"""Nombre de usuario unico y version de credencial para poder revocar sesiones

Revision ID: d1a3c5e7f9b2
Revises: c2e4a6b8d0f1
Create Date: 2026-08-31 10:00:00.000000

Dos agujeros de seguridad que venian juntos porque tienen la misma raiz: el
token identificaba al usuario por su nombre.

1. `usuarios.nombre` no era unico ni estaba indexado. La unicidad se validaba
   sólo en código, con lectura y despues escritura. Un administrador que
   renombraba al cajero `juan` a `juan.perez` y despues creaba otro usuario
   `juan` con rol ADMIN convertia la sesion abierta del cajero en sesion de
   administrador, sin que nadie hiciera nada malicioso.

2. Cambiar o reiniciar un PIN no sacaba de circulacion la sesion anterior. El
   docstring del endpoint decia que servia para eso y no lo hacia: sin `jti`
   ni version de credencial, el token viejo valia hasta doce horas mas.

El indice unico ademas saca el recorrido completo de la tabla que hacia cada
login.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1a3c5e7f9b2'
down_revision: Union[str, Sequence[str], None] = 'c2e4a6b8d0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conexion = op.get_bind()

    # Antes del UNIQUE hay que deduplicar: una base vieja puede tener nombres
    # repetidos, porque hasta ahora nada lo impedia. Se conserva el id mas bajo
    # (el original) y a los demas se les agrega el sufijo, en vez de borrarlos:
    # tienen ventas y movimientos colgando, y perderlos seria peor.
    repetidos = conexion.execute(sa.text(
        "SELECT nombre FROM usuarios GROUP BY nombre HAVING COUNT(*) > 1"
    )).fetchall()

    for (nombre,) in repetidos:
        filas = conexion.execute(
            sa.text("SELECT id FROM usuarios WHERE nombre = :n ORDER BY id"),
            {"n": nombre},
        ).fetchall()
        # El primero se queda con el nombre; el resto pasa a "nombre-2", "nombre-3"…
        for orden, (usuario_id,) in enumerate(filas[1:], start=2):
            conexion.execute(
                sa.text("UPDATE usuarios SET nombre = :nuevo WHERE id = :id"),
                {"nuevo": f"{nombre}-{orden}", "id": usuario_id},
            )

    op.add_column('usuarios', sa.Column(
        'credenciales_version', sa.Integer(), nullable=False, server_default='1',
    ))
    op.create_index('ix_usuarios_nombre', 'usuarios', ['nombre'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Los nombres deduplicados no se revierten: no hay forma de saber cuales
    # habia que volver a juntar, y volver a juntarlos seria reabrir el agujero.
    op.drop_index('ix_usuarios_nombre', table_name='usuarios')
    op.drop_column('usuarios', 'credenciales_version')
