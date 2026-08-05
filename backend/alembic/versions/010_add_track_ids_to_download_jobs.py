"""Add track_ids to download_jobs for track-based (BPM range) ZIP jobs.

Revision ID: 010
Revises: 009
Create Date: 2026-07-08

A download job is album-based (album_ids) by default; when track_ids is set,
the packer builds a flat "Artist - Title.ext" archive from individual tracks
instead (used by the BPM-range download).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "download_jobs",
        sa.Column(
            "track_ids",
            sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("download_jobs", "track_ids")
