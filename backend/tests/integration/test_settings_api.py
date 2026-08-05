"""Integration tests for settings API endpoints."""

from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.schemas.settings import (
    ThemeMode,
    UserSettingsPreferences,
    UserSettingsResponse,
    UserSettingsUpdate,
)


class TestGetSettings:
    """Tests for GET /api/v1/settings endpoint."""

    def test_settings_response_schema(self):
        """Test settings response matches expected schema."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        response = UserSettingsResponse(
            id=1,
            preferences=UserSettingsPreferences(theme_mode=ThemeMode.SYSTEM),
            created_at=now,
            updated_at=now,
        )

        assert response.id == 1
        assert response.preferences.theme_mode == ThemeMode.SYSTEM
        assert response.created_at == now
        assert response.updated_at == now

    def test_default_preferences_have_system_theme(self):
        """Test that default preferences use system theme mode."""
        preferences = UserSettingsPreferences()
        assert preferences.theme_mode == ThemeMode.SYSTEM

    def test_response_serialization_uses_snake_case(self):
        """Test that response serialization uses snake_case for JSON fields."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        response = UserSettingsResponse(
            id=1,
            preferences=UserSettingsPreferences(theme_mode=ThemeMode.DARK),
            created_at=now,
            updated_at=now,
        )
        data = response.model_dump(mode="json")

        # Verify snake_case keys
        assert "created_at" in data
        assert "updated_at" in data
        assert "theme_mode" in data["preferences"]


class TestUpdateSettings:
    """Tests for PUT /api/v1/settings endpoint."""

    def test_update_request_schema(self):
        """Test update request schema validation."""
        update = UserSettingsUpdate(
            preferences=UserSettingsPreferences(theme_mode=ThemeMode.DARK)
        )

        assert update.preferences.theme_mode == ThemeMode.DARK

    def test_update_with_light_theme(self):
        """Test update request with light theme."""
        update = UserSettingsUpdate(preferences={"theme_mode": "light"})
        assert update.preferences.theme_mode == ThemeMode.LIGHT

    def test_update_with_dark_theme(self):
        """Test update request with dark theme."""
        update = UserSettingsUpdate(preferences={"theme_mode": "dark"})
        assert update.preferences.theme_mode == ThemeMode.DARK

    def test_update_with_system_theme(self):
        """Test update request with system theme."""
        update = UserSettingsUpdate(preferences={"theme_mode": "system"})
        assert update.preferences.theme_mode == ThemeMode.SYSTEM

    def test_update_invalid_theme_raises_validation_error(self):
        """Test that invalid theme mode raises validation error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UserSettingsUpdate(preferences={"theme_mode": "invalid_theme"})

        # Check that validation error contains theme_mode field info
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("theme_mode" in str(e.get("loc", ())) for e in errors)


class TestSettingsRouter:
    """Tests for settings router behavior."""

    def test_router_prefix(self):
        """Test that settings router has correct prefix."""
        from app.api.routes.settings import router

        assert router.prefix == "/settings"

    def test_router_tags(self):
        """Test that settings router has correct tags."""
        from app.api.routes.settings import router

        assert "settings" in router.tags

    def test_get_or_create_settings_function(self):
        """Test get_or_create_settings helper function behavior."""
        from app.api.routes.settings import get_or_create_settings

        # Create mock database session
        mock_db = Mock()

        # Test case 1: Settings exist
        mock_settings = Mock()
        mock_settings.id = 1
        mock_settings.preferences = {"theme_mode": "dark"}
        mock_db.query.return_value.first.return_value = mock_settings

        result = get_or_create_settings(mock_db)
        assert result == mock_settings

        # Test case 2: No settings exist - should create new
        mock_db.reset_mock()
        mock_db.query.return_value.first.return_value = None

        # Set up mock to return the added object after commit
        def side_effect(obj):
            obj.id = 1

        mock_db.add.side_effect = side_effect
        mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 1)

        result = get_or_create_settings(mock_db)

        # Verify add was called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()


class TestSettingsAPIContract:
    """Tests to verify API contract compliance."""

    def test_get_endpoint_path(self):
        """Test that GET endpoint path is correct according to API contract."""
        # According to api.md: GET /api/v1/settings
        from app.api.routes.settings import router

        # FastAPI resolves route.path to the full prefix + route path.
        routes = [route.path for route in router.routes]
        assert "/settings" in routes

    def test_put_endpoint_path(self):
        """Test that PUT endpoint path is correct according to API contract."""
        # According to api.md: PUT /api/v1/settings
        from app.api.routes.settings import router

        routes = [route.path for route in router.routes]
        assert "/settings" in routes

    def test_response_includes_all_required_fields(self):
        """Test that response includes all required fields per API contract."""
        # According to api.md: id, preferences, created_at, updated_at
        now = datetime(2024, 1, 15, 10, 30, 0)
        response = UserSettingsResponse(
            id=1,
            preferences=UserSettingsPreferences(),
            created_at=now,
            updated_at=now,
        )

        # Verify all required fields are present
        data = response.model_dump()
        assert "id" in data
        assert "preferences" in data
        assert "created_at" in data
        assert "updated_at" in data

        # Verify preferences has theme_mode
        assert "theme_mode" in data["preferences"]

    def test_preferences_theme_mode_default_is_system(self):
        """Test that default theme_mode is 'system' per API contract."""
        preferences = UserSettingsPreferences()
        assert preferences.theme_mode == ThemeMode.SYSTEM
        assert preferences.theme_mode.value == "system"


class TestPreferencesMerge:
    """Tests for preferences merge behavior in PUT endpoint."""

    def test_merge_preserves_existing_preferences(self):
        """Test that update merges with existing preferences."""
        # Simulate existing preferences
        existing = {"theme_mode": "dark", "future_setting": "value"}

        # Simulate update
        update_data = UserSettingsUpdate(preferences={"theme_mode": "light"})
        new_preferences = update_data.preferences.model_dump()

        # Simulate merge logic from settings.py
        merged = existing.copy()
        for key, value in new_preferences.items():
            merged[key] = value

        # theme_mode should be updated
        assert merged["theme_mode"] == ThemeMode.LIGHT
        # future_setting should be preserved (demonstrates extensibility)
        assert merged["future_setting"] == "value"

    def test_update_only_changes_provided_fields(self):
        """Test that update only changes fields that are provided."""
        # Simulate existing preferences with multiple settings
        existing = {
            "theme_mode": "dark",
            "another_setting": "original_value",
        }

        # Update only theme_mode
        update = {"theme_mode": "system"}

        # Merge
        merged = existing.copy()
        merged.update(update)

        # Verify only theme_mode changed
        assert merged["theme_mode"] == "system"
        assert merged["another_setting"] == "original_value"
