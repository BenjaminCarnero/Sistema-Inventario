"""Indices en las columnas por las que se filtra todos los dias

Revision ID: f3c5e7a9b1d4
Revises: e2b4d6f8a0c3
Create Date: 2026-08-31 10:10:00.000000

Con doce productos y cuarenta ventas no se nota. Con un año de trabajo si:
todas estas consultas recorrian la tabla entera cada vez.

    arqueo y reportes por fecha  ->  SCAN ventas
    ventas de un cajero         ->  SCAN ventas
    detalle de una venta        ->  SCAN detalle_ventas
    historial de un producto    ->  SCAN movimientos_stock

`movimientos_stock` es la tabla que mas rapido crece de todo el sistema —una
fila por linea vendida, mas los ingresos y los ajustes— y es justo la que se
consultaba sin un solo indice.

El indice de `usuarios.nombre` no esta aca: lo crea la migracion
d1a3c5e7f9b2, donde ademas es UNIQUE.

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f3c5e7a9b1d4'
down_revision: Union[str, Sequence[str], None] = 'e2b4d6f8a0c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_ventas_fecha_hora', 'ventas', ['fecha_hora'])
    op.create_index('ix_ventas_usuario_id', 'ventas', ['usuario_id'])
    op.create_index('ix_detalle_ventas_venta_id', 'detalle_ventas', ['venta_id'])
    op.create_index('ix_detalle_ventas_producto_id', 'detalle_ventas', ['producto_id'])
    op.create_index('ix_movimientos_stock_producto_id', 'movimientos_stock', ['producto_id'])
    op.create_index('ix_movimientos_stock_fecha_hora', 'movimientos_stock', ['fecha_hora'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_movimientos_stock_fecha_hora', table_name='movimientos_stock')
    op.drop_index('ix_movimientos_stock_producto_id', table_name='movimientos_stock')
    op.drop_index('ix_detalle_ventas_producto_id', table_name='detalle_ventas')
    op.drop_index('ix_detalle_ventas_venta_id', table_name='detalle_ventas')
    op.drop_index('ix_ventas_usuario_id', table_name='ventas')
    op.drop_index('ix_ventas_fecha_hora', table_name='ventas')
