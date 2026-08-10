"""add proveedores y pedidos

Revision ID: f6b8d0c2e4a3
Revises: e5a7c9b1d3f4
Create Date: 2026-08-10

Cierra el ciclo del stock: hasta ahora bajaba con las ventas y subía a mano,
pero no quedaba registrado a quién se le compró ni qué está en camino.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6b8d0c2e4a3'
down_revision: Union[str, Sequence[str], None] = 'e5a7c9b1d3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'proveedores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('telefono', sa.String(length=30), nullable=True),
        sa.Column('email', sa.String(length=150), nullable=True),
        sa.Column('cuit', sa.String(length=20), nullable=True),
        sa.Column('notas', sa.String(length=500), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_proveedores_id'), 'proveedores', ['id'])
    op.create_index(op.f('ix_proveedores_nombre'), 'proveedores', ['nombre'], unique=True)

    op.create_table(
        'pedidos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('proveedor_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=True),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='PENDIENTE'),
        sa.Column('fecha_recepcion', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notas', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['proveedor_id'], ['proveedores.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pedidos_id'), 'pedidos', ['id'])
    op.create_index(op.f('ix_pedidos_proveedor_id'), 'pedidos', ['proveedor_id'])
    op.create_index(op.f('ix_pedidos_estado'), 'pedidos', ['estado'])

    op.create_table(
        'detalle_pedidos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pedido_id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('cantidad_recibida', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedidos.id']),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_detalle_pedidos_id'), 'detalle_pedidos', ['id'])
    op.create_index(op.f('ix_detalle_pedidos_producto_id'), 'detalle_pedidos', ['producto_id'])

    with op.batch_alter_table('productos') as batch:
        batch.add_column(sa.Column('proveedor_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('cantidad_pedido_habitual', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_productos_proveedor', 'proveedores', ['proveedor_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('productos') as batch:
        batch.drop_constraint('fk_productos_proveedor', type_='foreignkey')
        batch.drop_column('cantidad_pedido_habitual')
        batch.drop_column('proveedor_id')

    op.drop_table('detalle_pedidos')
    op.drop_table('pedidos')
    op.drop_table('proveedores')
