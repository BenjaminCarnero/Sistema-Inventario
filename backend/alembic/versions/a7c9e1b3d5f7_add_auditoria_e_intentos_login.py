"""add auditoria e intentos_login

Revision ID: a7c9e1b3d5f7
Revises: f6b8d0c2e4a3
Create Date: 2026-08-10

El stock ya dejaba historial; los pesos no. Y los intentos de login vivían en
memoria, así que reiniciar el servidor borraba el freno a la fuerza bruta.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c9e1b3d5f7'
down_revision: Union[str, Sequence[str], None] = 'f6b8d0c2e4a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'auditoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=True),
        sa.Column('entidad', sa.String(length=40), nullable=False),
        sa.Column('entidad_id', sa.Integer(), nullable=True),
        sa.Column('entidad_nombre', sa.String(length=150), nullable=True),
        sa.Column('accion', sa.String(length=20), nullable=False),
        sa.Column('campo', sa.String(length=60), nullable=True),
        sa.Column('valor_anterior', sa.Text(), nullable=True),
        sa.Column('valor_nuevo', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_auditoria_id'), 'auditoria', ['id'])
    op.create_index(op.f('ix_auditoria_fecha_hora'), 'auditoria', ['fecha_hora'])
    op.create_index(op.f('ix_auditoria_entidad'), 'auditoria', ['entidad'])

    op.create_table(
        'intentos_login',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario', sa.String(length=100), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_intentos_login_id'), 'intentos_login', ['id'])
    op.create_index(op.f('ix_intentos_login_usuario'), 'intentos_login', ['usuario'])
    op.create_index(op.f('ix_intentos_login_fecha_hora'), 'intentos_login', ['fecha_hora'])


def downgrade() -> None:
    op.drop_table('intentos_login')
    op.drop_table('auditoria')
