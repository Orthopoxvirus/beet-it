"""Add library path fields and slug

Revision ID: 002
Revises: 001
Create Date: 2024-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add slug column (unique, nullable initially for migration)
    op.add_column('libraries', sa.Column('slug', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_libraries_slug'), 'libraries', ['slug'], unique=True)

    # Add new path columns (nullable)
    op.add_column('libraries', sa.Column('database_path', sa.String(length=500), nullable=True))
    op.add_column('libraries', sa.Column('library_path', sa.String(length=500), nullable=True))
    op.add_column('libraries', sa.Column('import_path', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('libraries', 'import_path')
    op.drop_column('libraries', 'library_path')
    op.drop_column('libraries', 'database_path')
    op.drop_index(op.f('ix_libraries_slug'), table_name='libraries')
    op.drop_column('libraries', 'slug')
