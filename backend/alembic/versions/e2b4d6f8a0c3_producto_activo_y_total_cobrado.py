"""Baja logica de productos y el total que decia el ticket

Revision ID: e2b4d6f8a0c3
Revises: d1a3c5e7f9b2
Create Date: 2026-08-31 10:05:00.000000

`productos.activo`: hasta ahora un producto no se podia sacar de circulacion.
No hay `DELETE /productos` —y no puede haberlo, porque las ventas pasadas lo
referencian— asi que el catalogo solo crecia y lo discontinuado seguia
apareciendo en el POS para siempre.

`ventas.total_cobrado`: lo que decia el ticket que se le entrego al cliente.
En una venta offline el POS calcula el total con el catalogo y el IVA que tiene
guardados en el equipo; al sincronizar, el servidor lo recalcula con los suyos,
que es la regla correcta. Si el precio o la alicuota cambiaron mientras el
equipo estuvo sin señal, los dos numeros no coinciden. La diferencia ya existia
antes de esta columna: lo que no existia era forma de enterarse.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2b4d6f8a0c3'
down_revision: Union[str, Sequence[str], None] = 'd1a3c5e7f9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Todo lo que ya existe queda activo: hasta hoy no habia forma de dar de
    # baja nada, asi que ningun producto cargado estaba discontinuado.
    op.add_column('productos', sa.Column(
        'activo', sa.Boolean(), nullable=False, server_default='1',
    ))
    # Las ventas viejas quedan en NULL: son las que se registraron cuando el
    # total cobrado y el calculado eran el mismo numero por construccion.
    op.add_column('ventas', sa.Column('total_cobrado', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ventas', 'total_cobrado')
    op.drop_column('productos', 'activo')
