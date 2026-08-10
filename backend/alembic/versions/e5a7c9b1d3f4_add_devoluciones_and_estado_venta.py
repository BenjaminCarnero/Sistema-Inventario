"""Add devoluciones tables and ventas.estado

Revision ID: e5a7c9b1d3f4
Revises: d4f6b8c0e2a1
Create Date: 2026-08-10 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5a7c9b1d3f4'
down_revision: Union[str, Sequence[str], None] = 'd4f6b8c0e2a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'devoluciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venta_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('motivo', sa.String(length=255), nullable=True),
        sa.Column('total_devuelto', sa.Float(), nullable=False),
        sa.Column('es_anulacion', sa.Boolean(), nullable=True),
        sa.Column('metodo_devolucion', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['venta_id'], ['ventas.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_devoluciones_id'), 'devoluciones', ['id'], unique=False)
    op.create_index(op.f('ix_devoluciones_venta_id'), 'devoluciones', ['venta_id'], unique=False)

    op.create_table(
        'detalle_devoluciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('devolucion_id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('precio_unitario', sa.Float(), nullable=False),
        sa.Column('subtotal', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['devolucion_id'], ['devoluciones.id'], ),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_detalle_devoluciones_id'), 'detalle_devoluciones', ['id'], unique=False)

    # Las ventas que ya existían quedan como COMPLETADA
    op.add_column(
        'ventas',
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='COMPLETADA'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ventas', 'estado')

    op.drop_index(op.f('ix_detalle_devoluciones_id'), table_name='detalle_devoluciones')
    op.drop_table('detalle_devoluciones')

    op.drop_index(op.f('ix_devoluciones_venta_id'), table_name='devoluciones')
    op.drop_index(op.f('ix_devoluciones_id'), table_name='devoluciones')
    op.drop_table('devoluciones')
