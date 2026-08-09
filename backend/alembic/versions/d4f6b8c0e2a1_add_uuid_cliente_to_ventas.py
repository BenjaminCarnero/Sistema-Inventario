"""Add ventas.uuid_cliente for idempotent sync

Revision ID: d4f6b8c0e2a1
Revises: c3e5a7b9d1f2
Create Date: 2026-08-06 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f6b8c0e2a1'
down_revision: Union[str, Sequence[str], None] = 'c3e5a7b9d1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('ventas', sa.Column('uuid_cliente', sa.String(length=64), nullable=True))
    # Índice único: dos sincronizaciones de la misma venta no pueden coexistir.
    # Las ventas viejas quedan en NULL, que no participa de la restricción.
    op.create_index('ix_ventas_uuid_cliente', 'ventas', ['uuid_cliente'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ventas_uuid_cliente', table_name='ventas')
    op.drop_column('ventas', 'uuid_cliente')
