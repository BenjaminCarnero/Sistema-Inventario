"""Add monto_recibido and vuelto to Ventas

Revision ID: 3e8a130483a7
Revises: 76adc741716f
Create Date: 2026-07-03 20:35:32.384531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3e8a130483a7'
down_revision: Union[str, Sequence[str], None] = '76adc741716f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('ventas', sa.Column('monto_recibido', sa.Float(), nullable=True))
    op.add_column('ventas', sa.Column('vuelto', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ventas', 'vuelto')
    op.drop_column('ventas', 'monto_recibido')
