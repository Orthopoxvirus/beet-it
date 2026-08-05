"""Pydantic schemas for user settings API."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ThemeMode(str, Enum):
    """Available theme mode options.

    - LIGHT: Always use light theme
    - DARK: Always use dark theme
    - SYSTEM: Automatically match the operating system's theme setting
    """

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class UserSettingsPreferences(BaseModel):
    """User preferences stored in JSONB field.

    This schema defines the structure of the preferences object.
    It is designed for extensibility - new settings can be added
    as additional fields without requiring database migrations.
    """

    theme_mode: ThemeMode = Field(
        default=ThemeMode.SYSTEM,
        description="User's preferred theme mode",
    )


class UserSettingsResponse(BaseModel):
    """Response schema for user settings endpoints."""

    id: int = Field(..., description="Unique settings record identifier")
    preferences: UserSettingsPreferences = Field(
        ..., description="User preferences object"
    )
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last modification timestamp")

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    """Request schema for updating user settings."""

    preferences: UserSettingsPreferences = Field(
        ..., description="Preferences to update"
    )
