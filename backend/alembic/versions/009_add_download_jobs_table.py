"""Add download_jobs table for the multi-album Download Center.

Revision ID: 009
Revises: 008
Create Date: 2026-06-22

Creates the download_jobs table backing the Download Center feature: each row
is one user-gathered set of albums packed into a single ZIP archive
asynchronously, with packing progress and the on-disk archive location tracked
for download / deletion / expiry.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in tests).
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        'download_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('library_id', sa.Integer(), nullable=False),
        sa.Column('library_slug', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('album_ids', JSON_TYPE, nullable=False),
        sa.Column('album_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('filename', sa.String(512), nullable=True),
        sa.Column('zip_path', sa.String(1024), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('task_event_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['library_id'], ['libraries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_download_jobs_id', 'download_jobs', ['id'])
    op.create_index('ix_download_jobs_library_id', 'download_jobs', ['library_id'])
    op.create_index('ix_download_jobs_status', 'download_jobs', ['status'])
    op.create_index('ix_download_jobs_created_at', 'download_jobs', ['created_at'])
    op.create_index('ix_download_jobs_expires_at', 'download_jobs', ['expires_at'])
    op.create_index('ix_download_jobs_library_status', 'download_jobs', ['library_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_download_jobs_library_status', table_name='download_jobs')
    op.drop_index('ix_download_jobs_expires_at', table_name='download_jobs')
    op.drop_index('ix_download_jobs_created_at', table_name='download_jobs')
    op.drop_index('ix_download_jobs_status', table_name='download_jobs')
    op.drop_index('ix_download_jobs_library_id', table_name='download_jobs')
    op.drop_index('ix_download_jobs_id', table_name='download_jobs')
    op.drop_table('download_jobs')
