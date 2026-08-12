"""Add ventas.pago_referencia to tie a sale to its Mercado Pago payment

Revision ID: b1d3f5a7c9e2
Revises: a7c9e1b3d5f7
Create Date: 2026-08-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1d3f5a7c9e2'
down_revision: Union[str, Sequence[str], None] = 'a7c9e1b3d5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('ventas', sa.Column('pago_referencia', sa.String(length=64), nullable=True))
    # Único: un mismo cobro de Mercado Pago no puede dar por pagadas dos ventas.
    # Las ventas viejas y las que no son por QR quedan en NULL, que no participa
    # de la restricción.
    op.create_index('ix_ventas_pago_referencia', 'ventas', ['pago_referencia'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ventas_pago_referencia', table_name='ventas')
    op.drop_column('ventas', 'pago_referencia')
