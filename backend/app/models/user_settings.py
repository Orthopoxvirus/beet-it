"""User settings model for persisting user preferences."""

from sqlalchemy import Column, Integer, DateTime, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

# JSONB on PostgreSQL, plain JSON on other dialects (e.g. SQLite in tests).
# Keeps server-side JSON indexing on prod without breaking test infra.
JSONType = JSON().with_variant(JSONB, "postgresql")

from app.database import Base


class UserSettings(Base):
    """User settings model storing preferences in JSONB.

    This model stores user preferences in a flexible JSONB field,
    allowing for extensibility without requiring database migrations
    for each new setting.

    Initially supports anonymous users (no user_id), with the capability
    to add user_id foreign key when authentication is implemented.
    """

    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    # user_id = Column(Integer, ForeignKey("users.id"), unique=True)  # Add when auth exists
    preferences = Column(
        JSONType,
        nullable=False,
        default={"theme_mode": "system"},
        server_default='{"theme_mode": "system"}',
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
