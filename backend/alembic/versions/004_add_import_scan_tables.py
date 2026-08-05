"""Add import scan tables

Revision ID: 004
Revises: 003
Create Date: 2024-01-25 00:00:00.000000

This migration creates the import_scans and import_items tables for tracking
import folder scans and discovered files/folders.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create import_scans table
    op.create_table(
        'import_scans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('library_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('items_total', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('items_processed', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['library_id'], ['libraries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_import_scans_id'), 'import_scans', ['id'], unique=False)
    op.create_index(op.f('ix_import_scans_library_id'), 'import_scans', ['library_id'], unique=False)

    # Create import_items table
    op.create_table(
        'import_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('library_id', sa.Integer(), nullable=False),
        sa.Column('scan_id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=1000), nullable=False),
        sa.Column('directory', sa.String(length=1000), nullable=True),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('album', sa.String(length=255), nullable=True),
        sa.Column('album_artist', sa.String(length=255), nullable=True),
        sa.Column('artist', sa.String(length=255), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('track_number', sa.Integer(), nullable=True),
        sa.Column('genre', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='new'),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['library_id'], ['libraries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scan_id'], ['import_scans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('library_id', 'path', name='uq_import_items_library_path')
    )
    op.create_index(op.f('ix_import_items_id'), 'import_items', ['id'], unique=False)
    op.create_index(op.f('ix_import_items_library_id'), 'import_items', ['library_id'], unique=False)
    op.create_index(op.f('ix_import_items_scan_id'), 'import_items', ['scan_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_import_items_scan_id'), table_name='import_items')
    op.drop_index(op.f('ix_import_items_library_id'), table_name='import_items')
    op.drop_index(op.f('ix_import_items_id'), table_name='import_items')
    op.drop_table('import_items')
    op.drop_index(op.f('ix_import_scans_library_id'), table_name='import_scans')
    op.drop_index(op.f('ix_import_scans_id'), table_name='import_scans')
    op.drop_table('import_scans')
