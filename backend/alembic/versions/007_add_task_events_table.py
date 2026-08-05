"""Add task_events table for activity history.

Revision ID: 007
Revises: 006
Create Date: 2026-02-28

This migration creates the task_events table for storing permanent history
of all background task executions. This supports the Activity Monitor feature
which provides global visibility into task execution across all libraries.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'task_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_type', sa.String(20), nullable=False),
        sa.Column('library_id', sa.Integer(), nullable=True),
        sa.Column('library_slug', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.ForeignKeyConstraint(['library_id'], ['libraries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create individual indexes
    op.create_index('ix_task_events_id', 'task_events', ['id'])
    op.create_index('ix_task_events_library_id', 'task_events', ['library_id'])
    op.create_index('ix_task_events_task_type', 'task_events', ['task_type'])
    op.create_index('ix_task_events_status', 'task_events', ['status'])
    op.create_index('ix_task_events_started_at', 'task_events', ['started_at'])
    op.create_index('ix_task_events_completed_at', 'task_events', ['completed_at'])

    # Create composite indexes for common queries
    op.create_index('ix_task_events_library_type', 'task_events', ['library_id', 'task_type'])
    op.create_index('ix_task_events_status_started', 'task_events', ['status', 'started_at'])


def downgrade() -> None:
    op.drop_index('ix_task_events_status_started', table_name='task_events')
    op.drop_index('ix_task_events_library_type', table_name='task_events')
    op.drop_index('ix_task_events_completed_at', table_name='task_events')
    op.drop_index('ix_task_events_started_at', table_name='task_events')
    op.drop_index('ix_task_events_status', table_name='task_events')
    op.drop_index('ix_task_events_task_type', table_name='task_events')
    op.drop_index('ix_task_events_library_id', table_name='task_events')
    op.drop_index('ix_task_events_id', table_name='task_events')
    op.drop_table('task_events')
