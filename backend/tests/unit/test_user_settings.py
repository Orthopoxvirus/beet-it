"""Unit tests for UserSettings model and settings schemas."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.schemas.settings import (
    ThemeMode,
    UserSettingsPreferences,
    UserSettingsResponse,
    UserSettingsUpdate,
)


class TestThemeModeEnum:
    """Tests for ThemeMode enum."""

    def test_theme_mode_values(self):
        """Test that ThemeMode enum has correct values."""
        assert ThemeMode.LIGHT.value == "light"
        assert ThemeMode.DARK.value == "dark"
        assert ThemeMode.SYSTEM.value == "system"

    def test_theme_mode_from_string(self):
        """Test that ThemeMode can be created from string values."""
        assert ThemeMode("light") == ThemeMode.LIGHT
        assert ThemeMode("dark") == ThemeMode.DARK
        assert ThemeMode("system") == ThemeMode.SYSTEM

    def test_theme_mode_invalid_value(self):
        """Test that invalid theme mode value raises ValueError."""
        with pytest.raises(ValueError):
            ThemeMode("invalid")


class TestUserSettingsPreferences:
    """Tests for UserSettingsPreferences schema."""

    def test_default_theme_mode(self):
        """Test that default theme_mode is system."""
        preferences = UserSettingsPreferences()
        assert preferences.theme_mode == ThemeMode.SYSTEM

    def test_set_theme_mode_light(self):
        """Test setting theme_mode to light."""
        preferences = UserSettingsPreferences(theme_mode=ThemeMode.LIGHT)
        assert preferences.theme_mode == ThemeMode.LIGHT

    def test_set_theme_mode_dark(self):
        """Test setting theme_mode to dark."""
        preferences = UserSettingsPreferences(theme_mode=ThemeMode.DARK)
        assert preferences.theme_mode == ThemeMode.DARK

    def test_set_theme_mode_from_string(self):
        """Test setting theme_mode from string value."""
        preferences = UserSettingsPreferences(theme_mode="dark")
        assert preferences.theme_mode == ThemeMode.DARK

    def test_invalid_theme_mode_raises_error(self):
        """Test that invalid theme_mode raises ValidationError."""
        with pytest.raises(ValidationError):
            UserSettingsPreferences(theme_mode="invalid")

    def test_model_dump(self):
        """Test that preferences can be serialized to dict."""
        preferences = UserSettingsPreferences(theme_mode=ThemeMode.DARK)
        data = preferences.model_dump()
        assert data == {"theme_mode": ThemeMode.DARK}

    def test_model_dump_by_alias(self):
        """Test that model_dump produces correct JSON-serializable output."""
        preferences = UserSettingsPreferences(theme_mode=ThemeMode.DARK)
        data = preferences.model_dump(mode="json")
        assert data == {"theme_mode": "dark"}


class TestUserSettingsResponse:
    """Tests for UserSettingsResponse schema."""

    def test_valid_response(self):
        """Test creating a valid response."""
        now = datetime.now()
        response = UserSettingsResponse(
            id=1,
            preferences=UserSettingsPreferences(theme_mode=ThemeMode.DARK),
            created_at=now,
            updated_at=now,
        )
        assert response.id == 1
        assert response.preferences.theme_mode == ThemeMode.DARK
        assert response.created_at == now
        assert response.updated_at == now

    def test_response_from_dict_preferences(self):
        """Test creating response with dict preferences."""
        now = datetime.now()
        response = UserSettingsResponse(
            id=1,
            preferences={"theme_mode": "light"},
            created_at=now,
            updated_at=now,
        )
        assert response.preferences.theme_mode == ThemeMode.LIGHT

    def test_response_serialization(self):
        """Test response serialization to JSON."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        response = UserSettingsResponse(
            id=1,
            preferences=UserSettingsPreferences(theme_mode=ThemeMode.SYSTEM),
            created_at=now,
            updated_at=now,
        )
        data = response.model_dump(mode="json")
        assert data["id"] == 1
        assert data["preferences"]["theme_mode"] == "system"


class TestUserSettingsUpdate:
    """Tests for UserSettingsUpdate schema."""

    def test_valid_update(self):
        """Test creating a valid update request."""
        update = UserSettingsUpdate(
            preferences=UserSettingsPreferences(theme_mode=ThemeMode.DARK)
        )
        assert update.preferences.theme_mode == ThemeMode.DARK

    def test_update_from_dict(self):
        """Test creating update from nested dict."""
        update = UserSettingsUpdate(preferences={"theme_mode": "light"})
        assert update.preferences.theme_mode == ThemeMode.LIGHT

    def test_update_missing_preferences_raises_error(self):
        """Test that missing preferences field raises ValidationError."""
        with pytest.raises(ValidationError):
            UserSettingsUpdate()

    def test_update_invalid_theme_mode_raises_error(self):
        """Test that invalid theme_mode in update raises ValidationError."""
        with pytest.raises(ValidationError):
            UserSettingsUpdate(preferences={"theme_mode": "invalid"})


class TestUserSettingsModel:
    """Tests for UserSettings SQLAlchemy model structure."""

    def test_model_import(self):
        """Test that UserSettings model can be imported."""
        from app.models.user_settings import UserSettings
        from app.models import UserSettings as UserSettingsFromInit

        assert UserSettings is UserSettingsFromInit

    def test_model_tablename(self):
        """Test that model has correct table name."""
        from app.models.user_settings import UserSettings

        assert UserSettings.__tablename__ == "user_settings"

    def test_model_has_required_columns(self):
        """Test that model has all required columns."""
        from app.models.user_settings import UserSettings

        columns = [c.name for c in UserSettings.__table__.columns]
        assert "id" in columns
        assert "preferences" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_model_preferences_column_type(self):
        """Test that preferences column is a JSON/JSONB variant.

        The column is defined as `JSON().with_variant(JSONB, 'postgresql')` so
        PostgreSQL gets native JSONB while SQLite-in-tests gets portable JSON.
        Either side of that variant should satisfy the test.
        """
        from app.models.user_settings import UserSettings
        from sqlalchemy import JSON
        from sqlalchemy.dialects.postgresql import JSONB

        preferences_column = UserSettings.__table__.columns["preferences"]
        assert isinstance(preferences_column.type, (JSON, JSONB))

    def test_model_default_preferences(self):
        """Test that default preferences is set correctly."""
        from app.models.user_settings import UserSettings

        preferences_column = UserSettings.__table__.columns["preferences"]
        # Check the column has a default value
        assert preferences_column.default is not None
        assert preferences_column.default.arg == {"theme_mode": "system"}
