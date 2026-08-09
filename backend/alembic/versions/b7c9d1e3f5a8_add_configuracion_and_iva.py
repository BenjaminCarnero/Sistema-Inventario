"""Add configuracion table and IVA fields on ventas

Revision ID: b7c9d1e3f5a8
Revises: a1f2c3d4e5b6
Create Date: 2026-08-06 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c9d1e3f5a8'
down_revision: Union[str, Sequence[str], None] = 'a1f2c3d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'configuracion',
        sa.Column('clave', sa.String(length=60), nullable=False),
        sa.Column('valor', sa.String(length=500), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('categoria', sa.String(length=40), nullable=False),
        sa.Column('descripcion', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('clave')
    )
    op.create_index(op.f('ix_configuracion_clave'), 'configuracion', ['clave'], unique=False)

    op.add_column('ventas', sa.Column('iva_porcentaje', sa.Float(), nullable=True))
    op.add_column('ventas', sa.Column('iva_monto', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ventas', 'iva_monto')
    op.drop_column('ventas', 'iva_porcentaje')

    op.drop_index(op.f('ix_configuracion_clave'), table_name='configuracion')
    op.drop_table('configuracion')
