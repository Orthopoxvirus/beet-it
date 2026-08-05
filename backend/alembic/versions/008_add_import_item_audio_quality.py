"""Add audio quality columns to import_items

Revision ID: 008
Revises: 007
Create Date: 2026-06-04 00:00:00.000000

Adds container format and bitrate (kbps) to import_items so the import prepare
view can surface audio quality. Both columns are nullable; existing rows stay
NULL until the folder is re-scanned.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('import_items', sa.Column('format', sa.String(length=20), nullable=True))
    op.add_column('import_items', sa.Column('bitrate', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('import_items', 'bitrate')
    op.drop_column('import_items', 'format')
