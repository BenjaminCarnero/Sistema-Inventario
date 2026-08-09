"""Initial schema

Revision ID: 76adc741716f
Revises:
Create Date: 2026-05-21 22:23:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '76adc741716f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'usuarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('pin_acceso', sa.String(length=255), nullable=False),
        sa.Column('rol_id', sa.Integer(), nullable=True),
        sa.Column('estado', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_usuarios_id'), 'usuarios', ['id'], unique=False)

    op.create_table(
        'categorias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_categorias_id'), 'categorias', ['id'], unique=False)
    op.create_index(op.f('ix_categorias_nombre'), 'categorias', ['nombre'], unique=True)

    op.create_table(
        'productos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo_barras', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('precio_venta', sa.Float(), nullable=False),
        sa.Column('costo', sa.Float(), nullable=False),
        sa.Column('stock_actual', sa.Integer(), nullable=True),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['categoria_id'], ['categorias.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_productos_id'), 'productos', ['id'], unique=False)
    op.create_index(op.f('ix_productos_codigo_barras'), 'productos', ['codigo_barras'], unique=True)

    op.create_table(
        'ventas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('total', sa.Float(), nullable=False),
        sa.Column('metodo_pago', sa.String(length=50), nullable=True),
        sa.Column('estado_sincronizacion', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ventas_id'), 'ventas', ['id'], unique=False)

    op.create_table(
        'detalle_ventas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venta_id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('precio_unitario', sa.Float(), nullable=False),
        sa.Column('subtotal', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ),
        sa.ForeignKeyConstraint(['venta_id'], ['ventas.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_detalle_ventas_id'), 'detalle_ventas', ['id'], unique=False)

    op.create_table(
        'movimientos_stock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('tipo_movimiento', sa.String(length=50), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('motivo', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_movimientos_stock_id'), 'movimientos_stock', ['id'], unique=False)

    op.create_table(
        'cajas_turnos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fecha_apertura', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('monto_inicial', sa.Float(), nullable=False),
        sa.Column('fecha_cierre', sa.DateTime(timezone=True), nullable=True),
        sa.Column('monto_final_declarado', sa.Float(), nullable=True),
        sa.Column('diferencia_calculada', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cajas_turnos_id'), 'cajas_turnos', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('cajas_turnos')
    op.drop_table('movimientos_stock')
    op.drop_table('detalle_ventas')
    op.drop_table('ventas')
    op.drop_table('productos')
    op.drop_index(op.f('ix_categorias_nombre'), table_name='categorias')
    op.drop_index(op.f('ix_categorias_id'), table_name='categorias')
    op.drop_table('categorias')
    op.drop_table('usuarios')
