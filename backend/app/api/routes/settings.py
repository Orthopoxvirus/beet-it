"""API routes for user settings operations."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_settings import UserSettings
from app.schemas.settings import (
    UserSettingsPreferences,
    UserSettingsResponse,
    UserSettingsUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def get_or_create_settings(db: Session) -> UserSettings:
    """Get the current user settings, creating default if none exist.

    Since authentication is not yet implemented, this returns
    the first (and only) settings record, creating one if needed.

    Args:
        db: Database session.

    Returns:
        The UserSettings instance.
    """
    settings = db.query(UserSettings).first()
    if not settings:
        # Create default settings
        default_preferences = UserSettingsPreferences()
        settings = UserSettings(
            preferences=default_preferences.model_dump(),
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
        logger.info(f"Created default user settings with id={settings.id}")
    return settings


@router.get("", response_model=UserSettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """Get the current user's settings.

    If no settings record exists, creates one with default values
    and returns it.

    Returns:
        UserSettingsResponse: The current user settings.

    Raises:
        HTTPException: 500 if settings retrieval fails.
    """
    try:
        settings = get_or_create_settings(db)

        # Convert preferences dict to Pydantic model for validation
        preferences = UserSettingsPreferences(**settings.preferences)

        return UserSettingsResponse(
            id=settings.id,
            preferences=preferences,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )
    except Exception as e:
        logger.error(f"Failed to retrieve settings: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve settings",
        )


@router.put("", response_model=UserSettingsResponse)
def update_settings(
    update_data: UserSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Update the user's settings.

    Performs a shallow merge with existing preferences - only the
    fields provided in the request body are updated, other existing
    preferences are preserved.

    Args:
        update_data: The settings update request body.
        db: Database session.

    Returns:
        UserSettingsResponse: The updated user settings.

    Raises:
        HTTPException: 422 if validation fails, 500 if update fails.
    """
    try:
        settings = get_or_create_settings(db)

        # Merge new preferences with existing ones
        # This performs a shallow merge - provided fields override existing
        current_preferences = settings.preferences.copy()
        new_preferences = update_data.preferences.model_dump()

        # Update only the fields that were provided
        for key, value in new_preferences.items():
            current_preferences[key] = value

        # Update the settings record
        settings.preferences = current_preferences
        db.commit()
        db.refresh(settings)

        logger.info(f"Updated user settings id={settings.id}")

        # Convert preferences dict to Pydantic model for response
        preferences = UserSettingsPreferences(**settings.preferences)

        return UserSettingsResponse(
            id=settings.id,
            preferences=preferences,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update settings",
        )
