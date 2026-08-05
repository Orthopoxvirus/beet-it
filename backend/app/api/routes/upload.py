"""API routes for file upload operations."""

import aiofiles
import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.library import Library
from app.schemas.upload import (
    UploadResponse,
    UploadedFile,
    FileConflict,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

# Chunk size for streaming file writes (1MB)
CHUNK_SIZE = 1024 * 1024


def get_library_by_slug(db: Session, slug: str) -> Library:
    """Get a library by its slug, raising 404 if not found."""
    library = db.query(Library).filter(Library.slug == slug).first()
    if not library:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "LIBRARY_NOT_FOUND",
                "message": "Library not found",
            },
        )
    return library


def validate_and_sanitize_path(relative_path: str, import_folder: Path) -> Path:
    """
    Validate and sanitize a relative path for file upload.

    Args:
        relative_path: The relative path provided by the client.
        import_folder: The base import folder path.

    Returns:
        The resolved full path if valid.

    Raises:
        ValueError: If the path is invalid or attempts traversal.
    """
    # Reject empty paths
    if not relative_path or not relative_path.strip():
        raise ValueError("Empty path not allowed")

    # Reject null bytes
    if "\x00" in relative_path:
        raise ValueError("Null bytes not allowed in path")

    # Reject absolute paths
    if relative_path.startswith("/") or relative_path.startswith("\\"):
        raise ValueError("Absolute paths not allowed")

    # Split path and check for parent directory traversal
    # Handle both forward and back slashes
    normalized_path = relative_path.replace("\\", "/")
    path_parts = normalized_path.split("/")

    if ".." in path_parts:
        raise ValueError("Parent directory traversal not allowed")

    # Reject paths with just dots or empty segments after normalization
    for part in path_parts:
        if part == "." or part == "":
            # Allow empty only as trailing (handled by Path normalization)
            if part == "." and path_parts.index(part) != len(path_parts) - 1:
                continue  # Allow . in middle paths, but not for traversal

    # Resolve the full path and verify it's within import folder
    # Use the normalized path for Path operations
    full_path = (import_folder / normalized_path).resolve()
    import_folder_resolved = import_folder.resolve()

    # Ensure the resolved path is within the import folder
    try:
        full_path.relative_to(import_folder_resolved)
    except ValueError:
        raise ValueError("Path escapes import folder boundary")

    return full_path


def parse_paths_json(paths_json: Optional[str]) -> Optional[List[str]]:
    """
    Parse the paths JSON string.

    Args:
        paths_json: JSON-encoded string array of paths.

    Returns:
        List of paths or None if not provided.

    Raises:
        HTTPException: If the JSON is invalid.
    """
    if paths_json is None:
        return None

    try:
        paths = json.loads(paths_json)
        if not isinstance(paths, list):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_PATHS",
                    "message": "The 'paths' field must be a valid JSON array of strings",
                },
            )
        for p in paths:
            if not isinstance(p, str):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "INVALID_PATHS",
                        "message": "The 'paths' field must be a valid JSON array of strings",
                    },
                )
        return paths
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PATHS",
                "message": "The 'paths' field must be a valid JSON array of strings",
            },
        )


def validate_paths(
    files: List[UploadFile],
    paths: Optional[List[str]],
    import_folder: Path,
) -> List[Tuple[str, str, Path]]:
    """
    Validate all paths and return the resolved destinations.

    Args:
        files: List of upload files.
        paths: Optional list of relative paths.
        import_folder: The import folder path.

    Returns:
        List of tuples: (filename, relative_path, full_destination_path)

    Raises:
        HTTPException: For validation errors.
    """
    # Check path count matches file count
    if paths is not None and len(paths) != len(files):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PATH_COUNT_MISMATCH",
                "message": f"Number of paths ({len(paths)}) does not match number of files ({len(files)})",
            },
        )

    result = []
    invalid_paths_traversal = []
    invalid_paths_characters = []

    for i, file in enumerate(files):
        filename = file.filename or f"unnamed_file_{i}"

        if paths is not None:
            relative_path = paths[i]
        else:
            relative_path = filename

        try:
            full_path = validate_and_sanitize_path(relative_path, import_folder)
            result.append((filename, relative_path, full_path))
        except ValueError as e:
            error_msg = str(e)
            if "Null bytes" in error_msg:
                invalid_paths_characters.append(relative_path)
            else:
                invalid_paths_traversal.append(relative_path)

    # Report path traversal errors
    if invalid_paths_traversal:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PATH_TRAVERSAL",
                "message": "Invalid path detected: path contains directory traversal",
                "invalid_paths": invalid_paths_traversal,
            },
        )

    # Report invalid character errors
    if invalid_paths_characters:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PATH_CHARACTERS",
                "message": "Path contains invalid characters",
                "invalid_paths": invalid_paths_characters,
            },
        )

    return result


def check_conflicts(
    file_destinations: List[Tuple[str, str, Path]],
) -> List[FileConflict]:
    """
    Check for file conflicts at destination paths.

    Args:
        file_destinations: List of (filename, relative_path, full_path) tuples.

    Returns:
        List of FileConflict objects for any conflicting files.
    """
    conflicts = []
    for filename, relative_path, full_path in file_destinations:
        if full_path.exists():
            conflicts.append(FileConflict(filename=filename, path=relative_path))
    return conflicts


async def stream_to_file(upload_file: UploadFile, destination: Path) -> int:
    """
    Stream uploaded file to disk in chunks using async I/O.

    Args:
        upload_file: The FastAPI UploadFile object.
        destination: The destination path.

    Returns:
        The number of bytes written.
    """
    # Create parent directories (sync operation, but fast - only happens once per file)
    destination.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    # Use aiofiles for non-blocking file writes
    async with aiofiles.open(destination, "wb") as f:
        while True:
            chunk = await upload_file.read(CHUNK_SIZE)
            if not chunk:
                break
            await f.write(chunk)  # Non-blocking async write
            total_bytes += len(chunk)

    return total_bytes


@router.post("/libraries/{slug}/upload", response_model=UploadResponse)
async def upload_files(
    slug: str,
    files: List[UploadFile] = File(..., description="Files to upload"),
    paths: Optional[str] = Form(
        None,
        description="JSON array of relative paths corresponding to each file",
    ),
    db: Session = Depends(get_db),
):
    """
    Upload one or more files to a library's import folder.

    Supports both individual files and folder uploads with preserved directory structure.

    - **files**: One or more files to upload (multipart form data)
    - **paths**: Optional JSON array of relative paths to preserve folder structure

    Returns details of uploaded files on success.

    Security:
    - All paths are validated to prevent directory traversal attacks
    - Files can only be written within the library's import folder
    - Existing files are never overwritten (409 Conflict is returned)
    """
    # Check for empty request
    if not files or len(files) == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_REQUEST",
                "message": "No files provided in the upload request",
            },
        )

    # Check if all files have empty filenames (indicates no actual files uploaded)
    if all(not f.filename for f in files):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_REQUEST",
                "message": "No files provided in the upload request",
            },
        )

    # Get the library
    library = get_library_by_slug(db, slug)

    # Check if import path is configured
    if not library.import_path:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "NO_IMPORT_PATH",
                "message": "Library has no import path configured",
            },
        )

    import_folder = Path(library.import_path)

    # Parse paths JSON
    paths_list = parse_paths_json(paths)

    # Validate all paths
    file_destinations = validate_paths(files, paths_list, import_folder)

    # Check for conflicts before writing any files
    conflicts = check_conflicts(file_destinations)
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FILE_EXISTS",
                "message": "One or more files already exist at the destination",
                "conflicts": [c.model_dump() for c in conflicts],
            },
        )

    # Write all files
    uploaded_files = []
    created_dirs = set()

    try:
        for i, (filename, relative_path, full_path) in enumerate(file_destinations):
            # Track created directories for cleanup on failure
            parent = full_path.parent
            while parent != import_folder.resolve() and parent not in created_dirs:
                if not parent.exists():
                    created_dirs.add(parent)
                parent = parent.parent

            # Stream the file to disk
            try:
                size_bytes = await stream_to_file(files[i], full_path)
                uploaded_files.append(
                    UploadedFile(
                        filename=filename,
                        path=relative_path,
                        size_bytes=size_bytes,
                    )
                )
            except PermissionError as e:
                logger.error(f"Permission denied writing file {full_path}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "PERMISSION_DENIED",
                        "message": "Server lacks write permissions to the import folder",
                    },
                )
            except OSError as e:
                error_msg = str(e).lower()
                if "no space" in error_msg or "disk full" in error_msg:
                    logger.error(f"Disk full while writing {full_path}: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "code": "DISK_FULL",
                            "message": "Insufficient disk space for the upload",
                        },
                    )
                logger.error(f"Error writing file {full_path}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "WRITE_ERROR",
                        "message": "Failed to write file to disk",
                        "filename": filename,
                    },
                )

    except HTTPException:
        # Re-raise HTTP exceptions, but clean up successfully written files first
        for uploaded in uploaded_files:
            try:
                dest_path = (import_folder / uploaded.path).resolve()
                if dest_path.exists():
                    dest_path.unlink()
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up file during error handling: {cleanup_error}")
        raise

    except Exception as e:
        # Clean up on unexpected errors
        for uploaded in uploaded_files:
            try:
                dest_path = (import_folder / uploaded.path).resolve()
                if dest_path.exists():
                    dest_path.unlink()
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up file during error handling: {cleanup_error}")

        logger.error(f"Unexpected error during file upload: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"Failed to upload files: {str(e)}",
            },
        )

    # Success
    file_count = len(uploaded_files)
    message = f"Successfully uploaded {file_count} file{'s' if file_count != 1 else ''}"

    return UploadResponse(
        status="success",
        message=message,
        files_uploaded=file_count,
        files=uploaded_files,
    )
