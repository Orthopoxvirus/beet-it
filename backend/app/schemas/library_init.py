"""Pydantic schemas for library initialization API."""

from typing import Optional

from pydantic import BaseModel, Field


class PathStatusResponse(BaseModel):
    """Response for GET /api/v1/libraries/{slug}/config/path-status endpoint."""

    directory_exists: bool = Field(
        ...,
        description="Whether the library directory exists on disk"
    )
    database_exists: bool = Field(
        ...,
        description="Whether the beets database file exists on disk"
    )
    directory_path: Optional[str] = Field(
        default=None,
        description="The configured library directory path (null if not configured)"
    )
    database_path: Optional[str] = Field(
        default=None,
        description="The configured database file path (null if not configured)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "directory_exists": True,
                "database_exists": False,
                "directory_path": "/data/libraries/jazz",
                "database_path": "/data/databases/jazz.db"
            }
        }


class InitializeResponse(BaseModel):
    """Response for POST /api/v1/libraries/{slug}/config/initialize endpoint."""

    success: bool = Field(
        ...,
        description="Whether initialization completed successfully"
    )
    directory_created: bool = Field(
        ...,
        description="Whether the library directory was created (false if already existed)"
    )
    database_initialized: bool = Field(
        ...,
        description="Whether the database was initialized (false if already existed)"
    )
    message: str = Field(
        ...,
        description="Human-readable status message"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "directory_created": True,
                "database_initialized": True,
                "message": "Library resources initialized successfully"
            }
        }
