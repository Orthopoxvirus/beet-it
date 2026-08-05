"""Add user_settings table

Revision ID: 006
Revises: 005
Create Date: 2024-01-30 00:00:00.000000

This migration creates the user_settings table for persisting user preferences
such as theme mode. Uses JSONB for the preferences field to allow extensibility.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column(
            'preferences',
            JSONB(),
            nullable=False,
            server_default='{"theme_mode": "system"}',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_settings_id'), 'user_settings', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_settings_id'), table_name='user_settings')
    op.drop_table('user_settings')
