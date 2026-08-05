"""API endpoints for filesystem browsing and directory management."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.beets_config import (
    FilesystemBrowseResponse,
    FilesystemCreateRequest,
    FilesystemCreateResponse,
    ErrorResponse,
)
from app.services.filesystem_service import FilesystemService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/filesystem", tags=["filesystem"])


def get_filesystem_service() -> FilesystemService:
    """Dependency to get the filesystem service."""
    return FilesystemService()


@router.get(
    "/browse",
    response_model=FilesystemBrowseResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid path format"},
        403: {"model": ErrorResponse, "description": "Path outside allowed boundaries"},
        404: {"model": ErrorResponse, "description": "Directory not found"},
    },
)
def browse_directory(
    path: str = Query(default="/", description="Directory path to browse"),
    filesystem_service: FilesystemService = Depends(get_filesystem_service),
):
    """Browse the filesystem for directory selection in the file tree component.

    Lists directories at the specified path. Only paths within allowed mount
    boundaries can be browsed:
    - /data/libraries - Music library directories
    - /data/import - Import staging directories
    - /data/databases - Database file locations
    - /config - Configuration file locations
    """
    try:
        return filesystem_service.browse_directory(path)
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=str(e),
            headers={"X-Error-Code": "PATH_NOT_ALLOWED"},
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail="Directory not found",
            headers={"X-Error-Code": "DIRECTORY_NOT_FOUND"},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
            headers={"X-Error-Code": "INVALID_PATH"},
        )
    except Exception as e:
        logger.error(f"Unexpected error browsing directory: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to browse directory: {str(e)}",
            headers={"X-Error-Code": "INTERNAL_ERROR"},
        )


@router.post(
    "/browse",
    response_model=FilesystemCreateResponse,
    status_code=201,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid directory name"},
        403: {"model": ErrorResponse, "description": "Path outside allowed boundaries"},
        409: {"model": ErrorResponse, "description": "Directory already exists"},
        500: {"model": ErrorResponse, "description": "Failed to create directory"},
    },
)
def create_directory(
    request: FilesystemCreateRequest,
    filesystem_service: FilesystemService = Depends(get_filesystem_service),
):
    """Create a new directory within allowed mount boundaries.

    Creates a directory with the specified name within the given parent path.
    The parent path must be within allowed mount boundaries.
    """
    try:
        entry = filesystem_service.create_directory(request.path, request.name)
        return FilesystemCreateResponse(success=True, path=entry.path)
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=str(e),
            headers={"X-Error-Code": "PATH_NOT_ALLOWED"},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid directory name: {str(e)}",
            headers={"X-Error-Code": "INVALID_NAME"},
        )
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Directory already exists",
            headers={"X-Error-Code": "DIRECTORY_EXISTS"},
        )
    except OSError as e:
        logger.error(f"Failed to create directory: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create directory: {str(e)}",
            headers={"X-Error-Code": "CREATE_ERROR"},
        )
    except Exception as e:
        logger.error(f"Unexpected error creating directory: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create directory: {str(e)}",
            headers={"X-Error-Code": "INTERNAL_ERROR"},
        )
