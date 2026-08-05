"""Make slug column non-nullable

Revision ID: 003
Revises: 002
Create Date: 2024-01-20 00:00:00.000000

This migration makes the slug column non-nullable by:
1. Populating any NULL slugs from library names using slugify logic
2. Altering the column to be non-nullable
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from slugify import slugify


revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get connection for data migration
    connection = op.get_bind()

    # Find all libraries with NULL slugs
    result = connection.execute(
        sa.text("SELECT id, name FROM libraries WHERE slug IS NULL")
    )
    libraries_to_update = result.fetchall()

    # Get all existing slugs to handle collisions
    existing_slugs_result = connection.execute(
        sa.text("SELECT slug FROM libraries WHERE slug IS NOT NULL")
    )
    existing_slugs = {row[0] for row in existing_slugs_result.fetchall()}

    # Generate and update slugs for libraries with NULL slugs
    for library_id, name in libraries_to_update:
        base_slug = slugify(name, lowercase=True, separator="-")

        # Handle collision with numeric suffix
        slug = base_slug
        suffix = 2
        while slug in existing_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        # Update the library with the generated slug
        connection.execute(
            sa.text("UPDATE libraries SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": library_id}
        )
        existing_slugs.add(slug)

    # Now make the column non-nullable
    op.alter_column('libraries', 'slug',
                    existing_type=sa.String(length=255),
                    nullable=False)


def downgrade() -> None:
    # Make slug column nullable again
    op.alter_column('libraries', 'slug',
                    existing_type=sa.String(length=255),
                    nullable=True)
