"""Widen configuracion.valor to Text so it can hold an embedded logo

Revision ID: c3e5a7b9d1f2
Revises: b7c9d1e3f5a8
Create Date: 2026-08-06 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e5a7b9d1f2'
down_revision: Union[str, Sequence[str], None] = 'b7c9d1e3f5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite no soporta ALTER COLUMN; batch_alter_table recrea la tabla.
    with op.batch_alter_table('configuracion', schema=None) as batch_op:
        batch_op.alter_column(
            'valor',
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('configuracion', schema=None) as batch_op:
        batch_op.alter_column(
            'valor',
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=False,
        )
