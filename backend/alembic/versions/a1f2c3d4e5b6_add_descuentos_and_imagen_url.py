"""Add descuentos table, ventas.descuento_id and productos.imagen_url

Revision ID: a1f2c3d4e5b6
Revises: 3e8a130483a7
Create Date: 2026-08-06 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1f2c3d4e5b6'
down_revision: Union[str, Sequence[str], None] = '3e8a130483a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'descuentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('codigo_promocional', sa.String(length=50), nullable=True),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=True),
        sa.Column('fecha_inicio', sa.DateTime(), nullable=True),
        sa.Column('fecha_fin', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_descuentos_id'), 'descuentos', ['id'], unique=False)

    op.add_column('productos', sa.Column('imagen_url', sa.String(length=500), nullable=True))

    # SQLite no soporta agregar una FK con ALTER TABLE; usamos batch_alter_table
    # para que Alembic recree la tabla cuando el dialecto lo requiera.
    with op.batch_alter_table('ventas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('descuento_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_ventas_descuento_id', 'descuentos', ['descuento_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ventas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ventas_descuento_id', type_='foreignkey')
        batch_op.drop_column('descuento_id')

    op.drop_column('productos', 'imagen_url')

    op.drop_index(op.f('ix_descuentos_id'), table_name='descuentos')
    op.drop_table('descuentos')
