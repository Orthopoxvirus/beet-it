"""API endpoints for beets configuration management."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.library import Library
from app.schemas.beets_config import (
    BeetsConfigSchema,
    EmbyTestRequest,
    EmbyTestResponse,
    ErrorResponse,
)
from app.schemas.library_init import PathStatusResponse, InitializeResponse
from app.services.beets_config_service import BeetsConfigService
from app.services.emby_service import EmbyConnectionService
from app.services.library_provisioning import LibraryProvisioningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/libraries", tags=["config"])


def get_config_service() -> BeetsConfigService:
    """Dependency to get the beets config service."""
    return BeetsConfigService()


def get_emby_service() -> EmbyConnectionService:
    """Dependency to get the Emby connection service."""
    return EmbyConnectionService()


def get_provisioning_service() -> LibraryProvisioningService:
    """Dependency to get the library provisioning service."""
    return LibraryProvisioningService()


@router.get(
    "/{library_id}/config",
    response_model=BeetsConfigSchema,
    responses={
        404: {"model": ErrorResponse, "description": "Library or config not found"},
        500: {"model": ErrorResponse, "description": "Failed to parse config"},
    },
)
def get_library_config(
    library_id: int,
    db: Session = Depends(get_db),
    config_service: BeetsConfigService = Depends(get_config_service),
):
    """Retrieve the beets configuration for a library as a JSON structure.

    Parses the library's YAML config file and returns it as a structured JSON object.
    """
    # Get the library from database
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    # Check if config path is set
    if not library.config_path:
        raise HTTPException(
            status_code=404,
            detail="Configuration file not found for library",
            headers={"X-Error-Code": "CONFIG_NOT_FOUND"},
        )

    # Parse the config file
    try:
        config = config_service.parse_yaml_config(library.config_path)
        return config
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Configuration file not found for library",
            headers={"X-Error-Code": "CONFIG_NOT_FOUND"},
        )
    except ValueError as e:
        logger.error(f"Failed to parse config for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse configuration file: {str(e)}",
            headers={"X-Error-Code": "CONFIG_PARSE_ERROR"},
        )
    except Exception as e:
        logger.error(f"Unexpected error parsing config for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse configuration file: {str(e)}",
            headers={"X-Error-Code": "CONFIG_PARSE_ERROR"},
        )


@router.put(
    "/{library_id}/config",
    response_model=BeetsConfigSchema,
    responses={
        404: {"model": ErrorResponse, "description": "Library not found"},
        422: {"description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Failed to write config"},
    },
)
def update_library_config(
    library_id: int,
    config: BeetsConfigSchema,
    db: Session = Depends(get_db),
    config_service: BeetsConfigService = Depends(get_config_service),
):
    """Update the beets configuration for a library from a JSON payload.

    Validates the JSON payload, converts it to YAML format, and writes it to the
    library's configuration file.
    """
    # Get the library from database
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    # Check if config path is set
    if not library.config_path:
        raise HTTPException(
            status_code=404,
            detail="Configuration path not set for library",
            headers={"X-Error-Code": "CONFIG_NOT_FOUND"},
        )

    # Save the config file
    try:
        config_service.save_config(library.config_path, config)
        logger.info(f"Updated config for library {library_id}")
        return config
    except OSError as e:
        logger.error(f"Failed to write config for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write configuration file: {str(e)}",
            headers={"X-Error-Code": "CONFIG_WRITE_ERROR"},
        )
    except ValueError as e:
        # Raised when the existing on-disk config can't be parsed for merge —
        # we refuse to clobber it, so report the real cause, not a write error.
        logger.error(f"Failed to parse existing config for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse existing configuration file: {str(e)}",
            headers={"X-Error-Code": "CONFIG_PARSE_ERROR"},
        )
    except Exception as e:
        logger.error(f"Unexpected error writing config for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write configuration file: {str(e)}",
            headers={"X-Error-Code": "CONFIG_WRITE_ERROR"},
        )


@router.post(
    "/{library_id}/config/emby/test",
    response_model=EmbyTestResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Library not found"},
    },
)
async def test_emby_connection(
    library_id: int,
    request: EmbyTestRequest,
    db: Session = Depends(get_db),
    emby_service: EmbyConnectionService = Depends(get_emby_service),
):
    """Test the Emby server connection with provided credentials.

    Attempts to connect to the Emby server and authenticate using the provided
    credentials. Returns success/failure status and server information if successful.
    """
    # Verify library exists
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    # Test the connection
    result = await emby_service.test_connection(
        host=request.host,
        port=request.port,
        userid=request.userid,
        apikey=request.apikey,
    )

    return result


@router.get(
    "/{library_id}/config/path-status",
    response_model=PathStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Library or config not found"},
        500: {"model": ErrorResponse, "description": "Failed to parse config"},
    },
)
def get_path_status(
    library_id: int,
    db: Session = Depends(get_db),
    config_service: BeetsConfigService = Depends(get_config_service),
    provisioning_service: LibraryProvisioningService = Depends(get_provisioning_service),
):
    """Check existence status of library directory and database paths.

    Returns whether the configured library directory and database file
    exist on disk.
    """
    # Get the library from database by ID
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library:
        raise HTTPException(
            status_code=404,
            detail="Library not found",
            headers={"X-Error-Code": "LIBRARY_NOT_FOUND"},
        )

    # Check if config path is set
    if not library.config_path:
        raise HTTPException(
            status_code=404,
            detail="Configuration file not found for library",
            headers={"X-Error-Code": "CONFIG_NOT_FOUND"},
        )

    # Parse the config file to get paths
    try:
        config = config_service.parse_yaml_config(library.config_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Configuration file not found for library",
            headers={"X-Error-Code": "CONFIG_NOT_FOUND"},
        )
    except ValueError as e:
        logger.error(f"Failed to parse config for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse configuration file: {str(e)}",
            headers={"X-Error-Code": "CONFIG_PARSE_ERROR"},
        )

    # Get paths from config
    directory_path = config.directory if config.directory else None
    database_path = config.library if config.library else None

    # Check existence
    directory_exists, database_exists = provisioning_service.get_path_status(
        directory_path, database_path
    )

    return PathStatusResponse(
        directory_exists=directory_exists,
        database_exists=database_exists,
        directory_path=directory_path,
        database_path=database_path,
    )


@router.post(
    "/{library_id}/config/initialize",
    response_model=InitializeResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Library or config not found"},
        403: {"model": ErrorResponse, "description": "Path outside allowed boundaries"},
        500: {"model": ErrorResponse, "description": "Initialization failed"},
    },
)
def initialize_library(
    library_id: int,
    db: Session = Depends(get_db),
    config_service: BeetsConfigService = Depends(get_config_service),
    provisioning_service: LibraryProvisioningService = Depends(get_provisioning_service),
):
    """Initialize library resources.

    Creates the library directory if missing and initializes the beets
    database by running beet config -p. This operation is idempotent -
    existing resources are not modified.
    """
    # Get the library from database by ID
    library = db.query(Library).filter(Library.id == library_id).first()
    if not library:
        raise HTTPException(
            status_code=404,
            detail="Library not found",
            headers={"X-Error-Code": "LIBRARY_NOT_FOUND"},
        )

    # Check if config path is set and exists
    if not library.config_path:
        raise HTTPException(
            status_code=404,
            detail="Configuration file not found for library",
            headers={"X-Error-Code": "CONFIG_NOT_FOUND"},
        )

    # Parse the config file to get paths
    try:
        config = config_service.parse_yaml_config(library.config_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Configuration file not found for library",
            headers={"X-Error-Code": "CONFIG_NOT_FOUND"},
        )
    except ValueError as e:
        logger.error(f"Failed to parse config for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse configuration file: {str(e)}",
            headers={"X-Error-Code": "CONFIG_PARSE_ERROR"},
        )

    # Get paths from config
    directory_path = config.directory if config.directory else None
    database_path = config.library if config.library else None

    if not directory_path or not database_path:
        raise HTTPException(
            status_code=500,
            detail="Library directory or database path not configured in beets config",
            headers={"X-Error-Code": "PATHS_NOT_CONFIGURED"},
        )

    # Check if already initialized
    directory_exists, database_exists = provisioning_service.get_path_status(
        directory_path, database_path
    )

    if directory_exists and database_exists:
        return InitializeResponse(
            success=True,
            directory_created=False,
            database_initialized=False,
            message="Library resources already initialized",
        )

    # Initialize resources
    try:
        directory_created, database_initialized = provisioning_service.initialize_library_resources(
            config_path=library.config_path,
            directory_path=directory_path,
            database_path=database_path,
        )

        return InitializeResponse(
            success=True,
            directory_created=directory_created,
            database_initialized=database_initialized,
            message="Library resources initialized successfully",
        )

    except ValueError as e:
        # Path boundary violation
        raise HTTPException(
            status_code=403,
            detail=str(e),
            headers={"X-Error-Code": "PATH_OUTSIDE_BOUNDARY"},
        )

    except OSError as e:
        logger.error(f"Failed to create directory for library {library_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create directory: {str(e)}",
            headers={"X-Error-Code": "DIRECTORY_CREATION_FAILED"},
        )

    except RuntimeError as e:
        error_msg = str(e)
        if "timed out" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail=error_msg,
                headers={"X-Error-Code": "INIT_TIMEOUT"},
            )
        raise HTTPException(
            status_code=500,
            detail=error_msg,
            headers={"X-Error-Code": "DATABASE_INIT_FAILED"},
        )
