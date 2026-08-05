"""Initial migration - create libraries table

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'libraries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('path', sa.String(length=500), nullable=False),
        sa.Column('config_path', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_libraries_id'), 'libraries', ['id'], unique=False)
    op.create_index(op.f('ix_libraries_name'), 'libraries', ['name'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_libraries_name'), table_name='libraries')
    op.drop_index(op.f('ix_libraries_id'), table_name='libraries')
    op.drop_table('libraries')
