"""Add devoluciones.caja_turno_id so the arqueo knows which till paid

Revision ID: c2e4a6b8d0f1
Revises: b1d3f5a7c9e2
Create Date: 2026-08-12 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2e4a6b8d0f1'
down_revision: Union[str, Sequence[str], None] = 'b1d3f5a7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('devoluciones', sa.Column('caja_turno_id', sa.Integer(), nullable=True))
    op.create_index('ix_devoluciones_caja_turno_id', 'devoluciones', ['caja_turno_id'])
    # Las devoluciones viejas quedan en NULL: no hay forma de saber a qué turno
    # pertenecían. El cierre de caja las sigue contando por ventana de tiempo,
    # que es exactamente lo que hacía antes, así que nada cambia para atrás.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_devoluciones_caja_turno_id', table_name='devoluciones')
    op.drop_column('devoluciones', 'caja_turno_id')
