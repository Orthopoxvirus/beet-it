"""Add track_total to import_items

Revision ID: 005
Revises: 004
Create Date: 2024-01-25 00:00:00.000000

This migration adds the track_total column to the import_items table
to support displaying track numbers in "x/y" format (e.g., "3/12").
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add track_total column to import_items table
    op.add_column(
        'import_items',
        sa.Column('track_total', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('import_items', 'track_total')
