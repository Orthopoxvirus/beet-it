import re
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

# Regex pattern for valid slugs: lowercase alphanumeric + hyphens, no leading/trailing/consecutive hyphens
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SLUG_REGEX = re.compile(SLUG_PATTERN)


def validate_slug_format(slug: str) -> str:
    """Validate that a slug matches the required format.

    Args:
        slug: The slug to validate.

    Returns:
        The validated slug.

    Raises:
        ValueError: If the slug format is invalid.
    """
    if not slug:
        raise ValueError("Slug cannot be empty")
    if not SLUG_REGEX.match(slug):
        raise ValueError(
            f"Slug must contain only lowercase alphanumeric characters and hyphens, "
            f"cannot start or end with a hyphen, and cannot contain consecutive hyphens. "
            f"Pattern: {SLUG_PATTERN}"
        )
    return slug


class VerificationStatus(BaseModel):
    """Status information from the beets configuration verification step."""
    verified: bool
    config_path: Optional[str] = None
    error: Optional[str] = None
    timed_out: bool = False


class LibraryCreate(BaseModel):
    """Request body for creating a new library."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="URL-safe identifier. Auto-generated from name if not provided.",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_slug_format(v)
        return v


class LibraryAdopt(BaseModel):
    """Request body for *adopting* a pre-existing beets library.

    Unlike `LibraryCreate`, adoption does not provision filesystem resources
    and does not fail when files already exist at the configured paths —
    that's the whole point. The caller is responsible for ensuring the paths
    are valid and reachable by the backend + celery-worker containers
    (typically via a bind mount in docker-compose.override.yaml).

    All path fields are required. Paths must lie within the configured
    mount points (`LIBRARIES_PATH`, `DATABASES_PATH`, `CONFIG_PATH`,
    `IMPORT_PATH`); the endpoint enforces this to prevent writes outside
    the intended data area.
    """

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="URL-safe identifier for the library. Required for adoption.",
    )
    description: Optional[str] = None
    database_path: str = Field(
        ...,
        description='Container path to the beets SQLite DB (e.g. "/data/databases/rock.db")',
    )
    library_path: str = Field(
        ...,
        description='Container path to the organised music directory (e.g. "/data/libraries/rock")',
    )
    import_path: str = Field(
        ...,
        description='Container path where new files land for import (e.g. "/data/import/rock")',
    )
    config_path: str = Field(
        ...,
        description='Container path to the beets YAML config (e.g. "/config/rock.yaml")',
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        return validate_slug_format(v)


class LibraryUpdate(BaseModel):
    """Request body for updating an existing library."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New URL-safe identifier for the library.",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_slug_format(v)
        return v


class LibraryResponse(BaseModel):
    """Response body for library operations."""
    id: int
    name: str
    slug: str  # Non-optional - all libraries must have a slug
    description: Optional[str] = None
    config_path: Optional[str] = None
    database_path: Optional[str] = None
    library_path: Optional[str] = None
    import_path: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    verification_status: Optional[VerificationStatus] = None

    class Config:
        from_attributes = True


class LibraryListResponse(BaseModel):
    """Response body for listing libraries."""
    items: list[LibraryResponse]
    total: int
    skip: int
    limit: int


class DeleteResponse(BaseModel):
    """Response body for successful deletion."""
    status: str = "deleted"
    id: int
    resources_deleted: dict[str, bool]
