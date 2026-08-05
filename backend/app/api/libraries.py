import asyncio
import io
import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
import zipfile
from typing import Generator, Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.library import Library
from app.schemas.library import (
    LibraryAdopt,
    LibraryCreate,
    LibraryUpdate,
    LibraryResponse,
    LibraryListResponse,
    DeleteResponse,
    VerificationStatus,
    SLUG_PATTERN,
)
from app.schemas.album import (
    AlbumResponse,
    AlbumListResponse,
    AlbumLettersResponse,
    AlbumDetailResponse,
    TrackResponse,
    TrackListResponse,
    CoverUploadResponse,
    CoverUrlRequest,
    MoveAlbumRequest,
    MoveAlbumResponse,
    ConvertAlbumWavRequest,
    ConvertAlbumWavResponse,
    DeleteAlbumMode,
    DeleteAlbumResponse,
)
from app.schemas.download import AlbumSizeResponse
from app.schemas.import_tree import ImportFolderNode, ImportTreeResponse
from app.services.library_provisioning import LibraryProvisioningService, verify_library_config
from app.services.beets_library_service import BeetsLibraryService
from app.services.import_tree import ImportTreeService
from app.config import get_settings
from app.services.redis_keys import get_redis_key_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/libraries", tags=["libraries"])


def get_library_by_slug(db: Session, slug: str) -> Library:
    """Get a library by its slug, raising 404 if not found.

    Args:
        db: Database session.
        slug: The slug to look up.

    Returns:
        The Library object.

    Raises:
        HTTPException: 404 if the library is not found.
    """
    library = db.query(Library).filter(Library.slug == slug).first()
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    return library


def get_provisioning_service() -> LibraryProvisioningService:
    """Dependency to get the library provisioning service."""
    return LibraryProvisioningService()


def get_beets_library_service() -> BeetsLibraryService:
    """Dependency to get the beets library service."""
    return BeetsLibraryService()


def get_import_tree_service() -> ImportTreeService:
    """Dependency to get the import tree service."""
    return ImportTreeService()


@router.get("/", response_model=LibraryListResponse)
def list_libraries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List all libraries with pagination support."""
    total = db.query(Library).count()
    libraries = db.query(Library).offset(skip).limit(limit).all()
    return LibraryListResponse(
        items=libraries,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/", response_model=LibraryResponse, status_code=201)
def create_library(
    library: LibraryCreate,
    db: Session = Depends(get_db),
    provisioning_service: LibraryProvisioningService = Depends(get_provisioning_service),
):
    """Create a new library with automatic provisioning of beets configuration and directories.

    On successful creation, the system will:
    1. Validate the library name is unique
    2. Use provided slug or generate a filesystem-safe slug from the name
    3. Check for slug collision with existing files/directories
    4. Create the beets config file
    5. Create the library and import directories
    6. Verify the config file by running beets config -p
    7. Create the database record with all generated paths

    If any step fails (except verification), all created resources are cleaned up.
    Verification failures are reported in the response but do not block library creation.
    """
    # Check for existing library with the same name
    existing = db.query(Library).filter(Library.name == library.name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A library with this name already exists",
            headers={"X-Error-Code": "DUPLICATE_NAME"},
        )

    # Check for existing library with the same slug (if user-provided)
    if library.slug:
        existing_slug = db.query(Library).filter(Library.slug == library.slug).first()
        if existing_slug:
            raise HTTPException(
                status_code=409,
                detail=f"Slug '{library.slug}' is already in use by another library",
                headers={"X-Error-Code": "SLUG_COLLISION"},
            )

    # Get all existing slugs for collision handling during auto-generation
    existing_slugs = {lib.slug for lib in db.query(Library.slug).all() if lib.slug}

    provisioning_result = None
    try:
        # Provision filesystem resources (includes verification)
        provisioning_result = provisioning_service.provision_library(
            library.name,
            user_slug=library.slug,
            existing_slugs=existing_slugs,
        )
        paths = provisioning_result.paths
        verification = provisioning_result.verification

        # Create database record
        db_library = Library(
            name=library.name,
            slug=paths.slug,
            description=library.description,
            path=paths.library_path,  # Keep backward compatibility with 'path' field
            config_path=paths.config_path,
            database_path=paths.database_path,
            library_path=paths.library_path,
            import_path=paths.import_path,
        )
        db.add(db_library)
        db.commit()
        db.refresh(db_library)

        # Map verification result to response schema
        verification_status = VerificationStatus(
            verified=verification.success,
            config_path=verification.config_path,
            error=verification.error,
            timed_out=verification.timed_out,
        )

        # Log verification failures (library creation succeeded but verification didn't)
        if not verification.success:
            if verification.timed_out:
                logger.warning(
                    f"Library '{library.name}' created but config verification timed out"
                )
            else:
                logger.warning(
                    f"Library '{library.name}' created but config verification failed: "
                    f"{verification.error}"
                )

        # Build response with verification status
        return LibraryResponse(
            id=db_library.id,
            name=db_library.name,
            slug=db_library.slug,
            description=db_library.description,
            config_path=db_library.config_path,
            database_path=db_library.database_path,
            library_path=db_library.library_path,
            import_path=db_library.import_path,
            created_at=db_library.created_at,
            updated_at=db_library.updated_at,
            verification_status=verification_status,
        )

    except ValueError as e:
        # Slug collision error from provisioning service
        error_msg = str(e)
        if "already exists on the filesystem" in error_msg:
            raise HTTPException(
                status_code=409,
                detail=error_msg,
                headers={"X-Error-Code": "SLUG_COLLISION"},
            )
        raise HTTPException(status_code=400, detail=error_msg)

    except IntegrityError as e:
        # Database constraint violation (e.g., duplicate name/slug)
        db.rollback()
        if provisioning_result:
            provisioning_service.cleanup_on_failure(provisioning_result.paths)
        logger.error(f"Database integrity error during library creation: {e}")
        raise HTTPException(
            status_code=409,
            detail="A library with this name already exists",
            headers={"X-Error-Code": "DUPLICATE_NAME"},
        )

    except OSError as e:
        # Filesystem error during provisioning
        if provisioning_result:
            provisioning_service.cleanup_on_failure(provisioning_result.paths)
        logger.error(f"Filesystem error during library creation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create library directories: {str(e)}",
        )

    except Exception as e:
        # Unexpected error - clean up and re-raise
        db.rollback()
        if provisioning_result:
            provisioning_service.cleanup_on_failure(provisioning_result.paths)
        logger.error(f"Unexpected error during library creation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create library: {str(e)}",
        )


@router.post("/adopt", response_model=LibraryResponse, status_code=201)
def adopt_library(
    library: LibraryAdopt,
    db: Session = Depends(get_db),
    provisioning_service: LibraryProvisioningService = Depends(get_provisioning_service),
):
    """Register a *pre-existing* beets library without filesystem provisioning.

    Use this when you're migrating an already-organised beets library into this
    app — for example after bind-mounting `/srv/music/rock` into the stack.
    Unlike POST /libraries/ which refuses to create a library if any of the
    target paths already exist, this endpoint expects the paths to exist and
    validates that they're within the configured mount boundaries.

    The endpoint:
    1. Checks the app DB doesn't already have a library with this name or slug.
    2. Validates each path is inside the configured `libraries_path`,
       `databases_path`, `config_path`, or `import_path` mount (prevents writes
       to arbitrary filesystem locations).
    3. Runs `beet config -p` against the provided config_path to surface obvious
       config errors early (reported in `verification_status`; does not block).
    4. Creates the library record with the provided paths verbatim.

    No files are created or moved. Nothing is backed up. If you point at a live
    beets library, other `beet` processes writing to it concurrently is still a
    bad idea — stop external writers before adopting.
    """
    # --- 1. app-DB uniqueness -------------------------------------------------
    if db.query(Library).filter(Library.name == library.name).first():
        raise HTTPException(
            status_code=409,
            detail="A library with this name already exists",
            headers={"X-Error-Code": "DUPLICATE_NAME"},
        )
    if db.query(Library).filter(Library.slug == library.slug).first():
        raise HTTPException(
            status_code=409,
            detail=f"Slug '{library.slug}' is already in use by another library",
            headers={"X-Error-Code": "SLUG_COLLISION"},
        )

    # --- 2. path-boundary validation -----------------------------------------
    # Reuse the provisioning service's allow-list so adopted libraries can only
    # point at configured mounts. This stops a caller from registering
    # /etc/passwd as an "import path".
    settings = get_settings()
    allowed_roots = {
        "database_path": settings.databases_path,
        "library_path": settings.libraries_path,
        "import_path": settings.import_path,
        "config_path": settings.config_path,
    }
    for field_name, root in allowed_roots.items():
        value = getattr(library, field_name)
        # normpath handles trailing slashes / .. tricks
        normalised = os.path.normpath(value)
        if not normalised.startswith(os.path.normpath(root) + os.sep) and normalised != os.path.normpath(root):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{field_name}={value!r} is outside the allowed mount "
                    f"{root!r}. Adjust the path or extend the mount in docker-compose."
                ),
                headers={"X-Error-Code": "PATH_OUT_OF_BOUNDS"},
            )

    # --- 3. best-effort config verification -----------------------------------
    # Non-fatal: we still create the DB record so the user can fix the config
    # via the UI and try again.
    verification = verify_library_config(library.config_path)
    verification_status = VerificationStatus(
        verified=verification.success,
        config_path=verification.config_path,
        error=verification.error,
        timed_out=verification.timed_out,
    )
    if not verification.success:
        logger.warning(
            f"Library '{library.name}' adopted but config verification failed: "
            f"{verification.error or 'timed out' if verification.timed_out else 'unknown error'}"
        )

    # --- 4. create DB record --------------------------------------------------
    try:
        db_library = Library(
            name=library.name,
            slug=library.slug,
            description=library.description,
            path=library.library_path,  # legacy 'path' column
            config_path=library.config_path,
            database_path=library.database_path,
            library_path=library.library_path,
            import_path=library.import_path,
        )
        db.add(db_library)
        db.commit()
        db.refresh(db_library)
    except IntegrityError:
        db.rollback()
        # Extremely narrow race — uniqueness was checked above but lost a race.
        raise HTTPException(
            status_code=409,
            detail="A library with this name or slug already exists",
            headers={"X-Error-Code": "DUPLICATE"},
        )

    logger.info(f"Adopted existing library '{library.name}' with slug '{library.slug}'")

    return LibraryResponse(
        id=db_library.id,
        name=db_library.name,
        slug=db_library.slug,
        description=db_library.description,
        config_path=db_library.config_path,
        database_path=db_library.database_path,
        library_path=db_library.library_path,
        import_path=db_library.import_path,
        created_at=db_library.created_at,
        updated_at=db_library.updated_at,
        verification_status=verification_status,
    )


@router.get("/{slug}", response_model=LibraryResponse)
def get_library(slug: str, db: Session = Depends(get_db)):
    """Get a specific library by its slug."""
    return get_library_by_slug(db, slug)


@router.put("/{slug}", response_model=LibraryResponse)
def update_library(slug: str, library: LibraryUpdate, db: Session = Depends(get_db)):
    """Update a library's name, description, and/or slug.

    Name, description, and slug can be updated.
    Paths are immutable - changing the name or slug does NOT rename config files,
    database files, or directories.
    """
    db_library = get_library_by_slug(db, slug)

    update_data = library.model_dump(exclude_unset=True)

    # Check for duplicate name if name is being updated
    if "name" in update_data and update_data["name"] != db_library.name:
        existing = db.query(Library).filter(Library.name == update_data["name"]).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail="A library with this name already exists",
                headers={"X-Error-Code": "DUPLICATE_NAME"},
            )

    # Check for duplicate slug if slug is being updated
    if "slug" in update_data and update_data["slug"] != db_library.slug:
        existing = db.query(Library).filter(Library.slug == update_data["slug"]).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Slug '{update_data['slug']}' is already in use by another library",
                headers={"X-Error-Code": "SLUG_COLLISION"},
            )

    # Allow updating name, description, and slug (paths are immutable)
    allowed_fields = {"name", "description", "slug"}
    for key, value in update_data.items():
        if key in allowed_fields:
            setattr(db_library, key, value)

    try:
        db.commit()
        db.refresh(db_library)
        return db_library
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A library with this name or slug already exists",
            headers={"X-Error-Code": "DUPLICATE_NAME"},
        )


@router.delete("/{slug}", response_model=DeleteResponse)
def delete_library(
    slug: str,
    keep_config: bool = Query(True, description="If false, delete the beets config file"),
    keep_database: bool = Query(True, description="If false, delete the beets database file"),
    keep_folders: bool = Query(True, description="If false, delete library and import directories"),
    db: Session = Depends(get_db),
    provisioning_service: LibraryProvisioningService = Depends(get_provisioning_service),
):
    """Delete a library with optional selective cleanup of filesystem resources.

    By default, all filesystem resources are preserved (safe deletion).
    The database record is always deleted.

    Query parameters:
    - keep_config: If false, delete the beets config file (default: true)
    - keep_database: If false, delete the beets database file (default: true)
    - keep_folders: If false, delete library and import directories (default: true)
    """
    db_library = get_library_by_slug(db, slug)

    # Store paths before deletion
    config_path = db_library.config_path
    database_path = db_library.database_path
    library_path = db_library.library_path
    import_path = db_library.import_path
    deleted_id = db_library.id

    # Delete the database record first
    db.delete(db_library)
    db.commit()

    # Clean up filesystem resources based on query parameters
    resources_deleted = provisioning_service.cleanup_resources(
        config_path=config_path,
        database_path=database_path,
        library_path=library_path,
        import_path=import_path,
        keep_config=keep_config,
        keep_database=keep_database,
        keep_folders=keep_folders,
    )

    return DeleteResponse(
        status="deleted",
        id=deleted_id,
        resources_deleted=resources_deleted,
    )


@router.get("/{slug}/import-tree", response_model=ImportTreeResponse)
def get_import_tree(
    slug: str,
    db: Session = Depends(get_db),
    import_tree_service: ImportTreeService = Depends(get_import_tree_service),
):
    """Get the hierarchical folder tree for a library's import folder.

    Returns a tree structure of folders within the library's import_path,
    with album detection and multi-disc identification. Results are cached
    in Redis for 5 minutes; cache is invalidated when a scan completes.

    Security:
    - Only returns folders within the library's configured import_path
    - Excludes hidden folders (starting with '.')
    - Symlinks are only followed if they stay within the import_path

    Returns:
    - 200: Import tree structure (may be empty if no import_path or path doesn't exist)
    - 404: Library not found
    - 500: Filesystem access error
    """
    # Look up the library by slug
    library = get_library_by_slug(db, slug)

    # If import_path is not set, return empty tree
    if not library.import_path:
        return ImportTreeResponse(import_path=None, children=[])

    redis_manager = get_redis_key_manager(get_settings().redis_url)

    # Check Redis cache first
    cached_data = redis_manager.get_import_tree_cache(library.id)
    if cached_data is not None:
        logger.debug(f"Import tree cache hit for library {slug}")
        children = [ImportFolderNode.model_validate(node) for node in cached_data]
        return ImportTreeResponse(import_path=library.import_path, children=children)

    try:
        # Build the import tree (expensive filesystem scan)
        children = import_tree_service.build_import_tree(library.import_path)

        # Cache the result for 5 minutes
        children_data = [node.model_dump() for node in children]
        redis_manager.set_import_tree_cache(library.id, children_data, ttl_seconds=300)
        logger.debug(f"Import tree cached for library {slug}")

        return ImportTreeResponse(
            import_path=library.import_path,
            children=children,
        )

    except PermissionError as e:
        logger.error(f"Permission denied reading import folder {library.import_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to read import folder: permission denied",
        )

    except OSError as e:
        logger.error(f"Error reading import folder {library.import_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to read import folder: {str(e)}",
        )


@router.get("/{slug}/albums", response_model=AlbumListResponse)
def list_library_albums(
    slug: str,
    skip: int = Query(0, ge=0, description="Number of records to skip (offset)"),
    limit: int = Query(50, ge=1, le=5000, description="Maximum records to return (max: 5000)"),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """List all albums in a library's beets database with pagination support.

    Albums are sorted by album artist, then by album title.
    """
    # Look up the library by slug
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        albums, total = beets_service.get_albums(
            library.database_path, skip, limit, library_root=library.library_path
        )

        # Convert AlbumData to AlbumResponse
        items = [
            AlbumResponse(
                id=album.id,
                title=album.title,
                artist=album.artist,
                cover_art_path=album.cover_art_path,
                cover_version=album.cover_version,
            )
            for album in albums
        ]

        return AlbumListResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
        )

    except FileNotFoundError:
        # Database doesn't exist yet — initialize it by running beets with the library config.
        # Running `beet config -p` opens the library on startup, creating the database as a side effect.
        if library.config_path and os.path.isfile(library.config_path):
            logger.info(f"Initializing beets database for library '{slug}'")
            try:
                subprocess.run(
                    ["python", "-m", "beets", "-c", library.config_path, "config", "-p"],
                    capture_output=True,
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"beets init command failed: {e}")
            return AlbumListResponse(items=[], total=0, skip=skip, limit=limit)

        logger.error(f"Beets database not found: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except Exception as e:
        logger.error(f"Unexpected error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )


@router.get("/{slug}/albums/letters", response_model=AlbumLettersResponse)
def get_album_letters(
    slug: str,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Get the list of starting letters that have albums in this library.

    Returns an array of letters (A-Z) and '#' for albums starting with
    numbers or special characters. Letters without any albums are not included.
    """
    # Look up the library by slug
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        letters = beets_service.get_album_letters(library.database_path)
        return AlbumLettersResponse(letters=letters)

    except FileNotFoundError:
        # Database doesn't exist - return empty letters (library not yet initialized)
        return AlbumLettersResponse(letters=[])

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except Exception as e:
        logger.error(f"Unexpected error getting album letters: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )


# MIME type mapping for common image extensions
IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# MIME type mapping for common audio extensions
AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/mp4",
    ".wav": "audio/wav",
    ".wma": "audio/x-ms-wma",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}

# Cover-art validators + SSRF guard live in the cover_download service so the
# synchronous import pipeline and this async endpoint enforce identical rules.
# Re-exported here for the cover endpoints below and existing test imports.
from app.services.cover_art import get_art_filename  # noqa: E402
from app.services.cover_download import (  # noqa: F401,E402
    BLOCKED_IP_RANGES,
    IMAGE_EXTENSIONS,
    IMAGE_MAGIC_BYTES,
    MAX_COVER_ART_SIZE,
    CoverDownloadError,
    fetch_cover_bytes,
    is_private_ip,
    validate_image_format,
    write_cover_file,
)


def validate_path_in_library(track_path: str, library_path: str) -> bool:
    """Validate that a track path is within the library directory.

    Prevents path traversal attacks by ensuring the resolved path
    stays within the library directory.

    Args:
        track_path: The path to validate.
        library_path: The library root directory.

    Returns:
        True if path is valid, False if it escapes library directory.
    """
    try:
        # Resolve any symlinks and normalize paths
        real_track_path = os.path.realpath(track_path)
        real_library_path = os.path.realpath(library_path)

        # Check if the track path starts with the library path
        return real_track_path.startswith(real_library_path + os.sep) or real_track_path == real_library_path
    except (OSError, ValueError):
        return False


def resolve_track_path(track_path: str, library_path: Optional[str]) -> str:
    """Resolve a beets track path to an absolute filesystem path.

    Track paths in beets can be absolute (standard install) or relative to the
    library root — the lscr.io/linuxserver/beets image, for example, stores
    them relative. A relative path must be joined against the library
    root, otherwise os.path.exists() resolves it against the backend
    container's CWD ("/app") and every track 404s.
    """
    if track_path and not os.path.isabs(track_path) and library_path:
        return os.path.join(library_path.rstrip("/"), track_path)
    return track_path


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse HTTP Range header.

    Args:
        range_header: The Range header value (e.g., "bytes=0-1023").
        file_size: Total size of the file.

    Returns:
        Tuple of (start, end) byte positions, or None if invalid.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None

    try:
        range_spec = range_header[6:]  # Remove "bytes=" prefix
        if "-" not in range_spec:
            return None

        parts = range_spec.split("-", 1)
        start_str, end_str = parts[0].strip(), parts[1].strip()

        if start_str == "":
            # Suffix range: -500 means last 500 bytes
            suffix_length = int(end_str)
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        elif end_str == "":
            # Range from start to end: 500-
            start = int(start_str)
            end = file_size - 1
        else:
            # Explicit range: 0-1023
            start = int(start_str)
            end = min(int(end_str), file_size - 1)

        if start > end or start >= file_size or start < 0:
            return None

        return (start, end)
    except (ValueError, IndexError):
        return None


def iter_file(
    file_path: str, start: int = 0, end: int | None = None, chunk_size: int = 1024 * 1024
) -> Generator[bytes, None, None]:
    """Generator that yields chunks of a file.

    Args:
        file_path: Path to the file to read.
        start: Starting byte position.
        end: Ending byte position (inclusive), or None for end of file.
        chunk_size: Size of chunks to yield (default 1MB).

    Yields:
        Chunks of file data.
    """
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = (end - start + 1) if end is not None else None

        while True:
            read_size = min(chunk_size, remaining) if remaining else chunk_size
            data = f.read(read_size)
            if not data:
                break
            yield data
            if remaining is not None:
                remaining -= len(data)
                if remaining <= 0:
                    break


def sanitize_filename_component(name: str, fallback: str) -> str:
    """Make `name` safe to use as a single path component in a zip entry or
    Content-Disposition filename.

    Strips path separators and non-printable characters so a track titled
    "AC/DC" or one carrying control bytes can't escape its directory or break
    the archive. Returns `fallback` if nothing printable survives.
    """
    cleaned = name.replace("/", "_").replace("\\", "_").replace("\x00", "")
    cleaned = "".join(c for c in cleaned if c.isprintable()).strip()
    # Trailing dots/spaces are illegal on Windows and confuse some unzippers.
    cleaned = cleaned.rstrip(". ")
    return cleaned or fallback


class _ZipStreamSink(io.RawIOBase):
    """Write-only, non-seekable sink that buffers what zipfile emits so a
    generator can drain and yield it.

    Because this object has no usable ``seek``/``tell``, zipfile falls back to
    writing data descriptors after each entry instead of rewinding to patch
    the local header — exactly what we need to stream an archive whose total
    size isn't known up front. Every mainstream unzip understands descriptors.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, b) -> int:
        self._buffer.extend(b)
        return len(b)

    def drain(self) -> bytes:
        chunk = bytes(self._buffer)
        del self._buffer[:]
        return chunk


def iter_album_zip(
    files: list[tuple[str, str]], chunk_size: int = 1024 * 1024
) -> Generator[bytes, None, None]:
    """Yield a ZIP archive of `files` without buffering it whole in memory.

    Args:
        files: List of (absolute_path, arcname) pairs. arcname is the name the
            entry gets inside the archive.
        chunk_size: Bytes read from each source file per iteration.

    Audio files are stored uncompressed (ZIP_STORED) — they're already
    compressed, so deflate would burn CPU for a fraction of a percent. A file
    that can't be opened is skipped with a warning rather than aborting the
    whole download (it would corrupt the archive mid-stream and the status code
    is already sent).
    """
    sink = _ZipStreamSink()
    with zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for path, arcname in files:
            try:
                src = open(path, "rb")
            except OSError:
                logger.warning("Skipping unreadable track in album zip: %s", path)
                continue
            with src:
                zinfo = zipfile.ZipInfo(arcname)
                zinfo.compress_type = zipfile.ZIP_STORED
                with zf.open(zinfo, mode="w") as dest:
                    while True:
                        data = src.read(chunk_size)
                        if not data:
                            break
                        dest.write(data)
                        chunk = sink.drain()
                        if chunk:
                            yield chunk
            chunk = sink.drain()
            if chunk:
                yield chunk
    # The closing ZipFile context writes the central directory; flush it out.
    tail = sink.drain()
    if tail:
        yield tail


_THUMB_CACHE_DIR = "/tmp/beet-it-thumb-cache"
_THUMB_ALLOWED_SIZES = frozenset({64, 128, 192, 256, 384, 512, 768, 1024})


def _resolve_thumbnail(source_path: str, slug: str, album_id: int, size: int) -> str:
    """Return a path to a WebP thumbnail of `source_path`, generating it on
    demand and caching to disk so subsequent requests are an O(1) sendfile.

    The cache lives at /tmp/beet-it-thumb-cache and is invalidated by source
    file mtime — if the user replaces the cover art, the next request
    regenerates the thumbnail. Output is WebP at quality 80, which is small
    (~20–40 KB at 256px) and supported by every modern browser.
    """
    from PIL import Image  # local import — Pillow is heavy at module level

    src_mtime = int(os.path.getmtime(source_path))
    cache_name = f"{slug}_{album_id}_{size}_{src_mtime}.webp"
    cache_path = os.path.join(_THUMB_CACHE_DIR, cache_name)
    if os.path.exists(cache_path):
        return cache_path

    os.makedirs(_THUMB_CACHE_DIR, exist_ok=True)

    # Drop thumbnails of older cover versions for this album+size — the
    # mtime-keyed names would otherwise accumulate forever after replaces.
    stale_prefix = f"{slug}_{album_id}_{size}_"
    try:
        for name in os.listdir(_THUMB_CACHE_DIR):
            if (
                name.startswith(stale_prefix)
                and name.endswith(".webp")
                and name != cache_name
            ):
                try:
                    os.unlink(os.path.join(_THUMB_CACHE_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass

    with Image.open(source_path) as img:
        # Pillow's `thumbnail` keeps aspect ratio and never upscales — covers
        # smaller than the requested size are returned at their native size.
        img.thumbnail((size, size), Image.LANCZOS)
        # Drop alpha when the source has it (most JPEGs don't, but PNG covers
        # do); RGB compresses tighter and the cards behind have an opaque
        # background anyway.
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # Atomic write: render to a temp file in the same directory, then
        # rename. Two parallel requests for the same key won't tear.
        tmp_path = cache_path + ".tmp"
        img.save(tmp_path, "WEBP", quality=80, method=6)
        os.replace(tmp_path, cache_path)
    return cache_path


@router.get("/{slug}/albums/{album_id}/cover")
def get_album_cover(
    slug: str,
    album_id: int,
    size: Optional[int] = Query(
        None,
        description=(
            "Optional thumbnail size in pixels (longest edge). When set, "
            "returns a cached WebP thumbnail instead of the original. "
            "Allowed values: 64, 128, 192, 256, 384, 512, 768, 1024."
        ),
    ),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Serve the album cover art image file.

    Returns the cover art image with appropriate Content-Type header and
    caching headers for optimal performance. Includes fallback discovery
    when artpath is null or file doesn't exist. Pass ?size=<px> to get a
    cached WebP thumbnail rendered with Pillow — the original artwork can
    be multi-megabyte, which makes grid views (artist mosaics etc.) unbearably
    slow without resizing.
    """
    # Look up the library by slug
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        # Check if album exists
        if not beets_service.album_exists(library.database_path, album_id):
            raise HTTPException(status_code=404, detail="Album not found")

        # Get Redis manager for caching
        redis_manager = get_redis_key_manager(get_settings().redis_url)

        # Get the cover art path with fallback discovery. Pass the library's
        # `directory:` so relative artpaths (lscr.io/linuxserver/beets quirk)
        # resolve against the right root instead of the container's CWD.
        cover_path = beets_service.get_album_cover_path_with_fallback(
            library.database_path,
            album_id,
            redis_manager=redis_manager,
            library_root=library.library_path,
        )

        if not cover_path:
            raise HTTPException(
                status_code=404,
                detail="Cover art not available for this album",
            )

        # Check if the file exists (should be redundant but safety check)
        if not os.path.exists(cover_path):
            logger.warning(f"Cover art file not found: {cover_path}")
            raise HTTPException(
                status_code=404,
                detail="Cover art file not found",
            )

        # Thumbnail variant (cached WebP) — used by the artist + folder
        # 2x2 mosaics where serving the original 4x for every card would be
        # ruinous. Whitelist of sizes keeps the on-disk cache bounded.
        if size is not None:
            if size not in _THUMB_ALLOWED_SIZES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Unsupported size. Allowed values: "
                        + ", ".join(str(s) for s in sorted(_THUMB_ALLOWED_SIZES))
                    ),
                )
            try:
                thumb_path = _resolve_thumbnail(cover_path, slug, album_id, size)
            except Exception as thumb_err:
                logger.error(
                    f"Failed to render cover thumbnail for album {album_id}: "
                    f"{thumb_err}"
                )
                # Fall through to the original on render failure rather than
                # 500'ing — a slow page beats a broken one.
            else:
                return FileResponse(
                    path=thumb_path,
                    media_type="image/webp",
                    headers={
                        "Cache-Control": "public, max-age=604800, immutable",
                    },
                )

        # Determine content type from file extension
        _, ext = os.path.splitext(cover_path.lower())
        media_type = IMAGE_MIME_TYPES.get(ext)

        if not media_type:
            # Fall back to mimetypes module
            media_type, _ = mimetypes.guess_type(cover_path)
            if not media_type:
                media_type = "application/octet-stream"

        # Return the file with caching headers
        return FileResponse(
            path=cover_path,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=86400",
            },
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except FileNotFoundError:
        logger.error(f"Beets database not found: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except Exception as e:
        logger.error(f"Unexpected error serving cover art: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to serve cover art: {str(e)}",
        )


@router.get("/{slug}/albums/{album_id}", response_model=AlbumDetailResponse)
def get_album_detail(
    slug: str,
    album_id: int,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Get detailed album metadata.

    Returns complete album metadata including track count, total duration,
    disc count, and other details.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        album = beets_service.get_album_by_id(
            library.database_path, album_id, library_root=library.library_path
        )

        if album is None:
            raise HTTPException(status_code=404, detail="Album not found")

        return AlbumDetailResponse(
            id=album.id,
            title=album.title,
            artist=album.artist,
            year=album.year,
            genre=album.genre,
            label=album.label,
            total_tracks=album.total_tracks,
            total_duration=album.total_duration,
            cover_art_path=album.cover_art_path,
            cover_version=album.cover_version,
            disc_count=album.disc_count,
            added=album.added,
            album_type=album.album_type,
            mb_albumid=album.mb_albumid,
            format=album.format,
            bitrate=album.bitrate,
            sample_rate=album.sample_rate,
            bit_depth=album.bit_depth,
            channels=album.channels,
        )

    except HTTPException:
        raise

    except FileNotFoundError:
        logger.error(f"Beets database not found: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )


@router.get("/{slug}/albums/{album_id}/tracks", response_model=TrackListResponse)
def get_album_tracks(
    slug: str,
    album_id: int,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Get all tracks for an album.

    Returns tracks ordered by disc number and track number.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        # First check if album exists
        if not beets_service.album_exists(library.database_path, album_id):
            raise HTTPException(status_code=404, detail="Album not found")

        tracks = beets_service.get_album_tracks(library.database_path, album_id)

        items = [
            TrackResponse(
                id=track.id,
                title=track.title,
                artist=track.artist,
                album=track.album,
                album_id=track.album_id,
                track_number=track.track_number,
                disc_number=track.disc_number,
                duration=track.duration,
                format=track.format,
                bitrate=track.bitrate,
                sample_rate=track.sample_rate,
                channels=track.channels,
                file_size=track.file_size,
                mb_trackid=track.mb_trackid,
            )
            for track in tracks
        ]

        return TrackListResponse(items=items, total=len(items))

    except HTTPException:
        raise

    except FileNotFoundError:
        logger.error(f"Beets database not found: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )


@router.get("/{slug}/albums/{album_id}/download")
def download_album_zip(
    slug: str,
    album_id: int,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Download an entire album as a streamed ZIP archive.

    Bundles every track file of the album into one uncompressed ZIP and streams
    it, so large albums don't have to be assembled in memory or staged on disk
    first. Tracks whose files are missing or escape the library directory are
    skipped; a 404 is returned only when the album has no downloadable files.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        album = beets_service.get_album_by_id(library.database_path, album_id)
        if album is None:
            raise HTTPException(status_code=404, detail="Album not found")

        tracks = beets_service.get_album_tracks(library.database_path, album_id)

        # Multi-disc albums prefix the disc number so tracks from different
        # discs don't collide on "01 - ...".
        multi_disc = len({t.disc_number for t in tracks if t.disc_number}) > 1

        files: list[tuple[str, str]] = []
        used_names: set[str] = set()
        for index, track in enumerate(tracks, start=1):
            absolute_path = resolve_track_path(track.path or "", library.library_path)
            if not absolute_path or not os.path.exists(absolute_path):
                logger.warning("Album zip: track file missing, skipping: %s", absolute_path)
                continue
            if library.library_path and not validate_path_in_library(
                absolute_path, library.library_path
            ):
                logger.warning(f"Path traversal attempt detected: {absolute_path}")
                continue

            ext = os.path.splitext(absolute_path)[1]
            track_no = track.track_number or index
            title = sanitize_filename_component(track.title or "", f"Track {index}")
            prefix = f"{track.disc_number or 1}-" if multi_disc else ""
            base = f"{prefix}{track_no:02d} - {title}"

            # Guard against duplicate entry names (e.g. two untitled tracks).
            candidate, n = f"{base}{ext}", 1
            while candidate in used_names:
                n += 1
                candidate = f"{base} ({n}){ext}"
            used_names.add(candidate)
            files.append((absolute_path, candidate))

        if not files:
            raise HTTPException(status_code=404, detail="No downloadable tracks found")

        label = f"{album.artist} - {album.title}" if album.artist else (album.title or "")
        zip_basename = sanitize_filename_component(label, f"album-{album_id}")
        ascii_name = (
            zip_basename.encode("ascii", "ignore").decode("ascii").replace('"', "").strip()
            or f"album-{album_id}"
        )
        # RFC 6266: ASCII filename for old clients, filename* for the real
        # (possibly non-ASCII) name modern browsers prefer.
        disposition = (
            f'attachment; filename="{ascii_name}.zip"; '
            f"filename*=UTF-8''{quote(zip_basename + '.zip')}"
        )

        # Zipping/streaming outlives this handler; release the DB connection
        # now so it doesn't sit "idle in transaction" for the whole download.
        db.close()

        return StreamingResponse(
            iter_album_zip(files),
            media_type="application/zip",
            headers={
                "Content-Disposition": disposition,
                "Cache-Control": "no-store",
            },
        )

    except HTTPException:
        raise

    except FileNotFoundError:
        logger.error(f"Beets database not found: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )


@router.get("/{slug}/albums/{album_id}/size", response_model=AlbumSizeResponse)
def get_album_size(
    slug: str,
    album_id: int,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Total on-disk size of an album's track files.

    Powers the Download Center's gathering bar, which sums the size of selected
    albums. ``get_album_tracks`` already computes each track's ``file_size``
    (0 for missing files), so this is a cheap aggregate.
    """
    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    album = beets_service.get_album_by_id(library.database_path, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")

    # Pass library_path so relative beets paths resolve on disk — otherwise
    # every track sizes to 0 and the gathering bar shows "0 B".
    tracks = beets_service.get_album_tracks(
        library.database_path, album_id, library_root=library.library_path
    )
    size_bytes = sum(t.file_size for t in tracks if t.file_size)
    track_count = sum(1 for t in tracks if t.file_size)
    return AlbumSizeResponse(size_bytes=size_bytes, track_count=track_count)


@router.get("/{slug}/tracks/{track_id}", response_model=TrackResponse)
def get_track(
    slug: str,
    track_id: int,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Get track metadata.

    Returns metadata for a specific track including title, artist, duration, format, etc.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        track = beets_service.get_track_by_id(library.database_path, track_id)

        if track is None:
            raise HTTPException(status_code=404, detail="Track not found")

        return TrackResponse(
            id=track.id,
            title=track.title,
            artist=track.artist,
            album=track.album,
            album_id=track.album_id,
            track_number=track.track_number,
            disc_number=track.disc_number,
            duration=track.duration,
            format=track.format,
            bitrate=track.bitrate,
            sample_rate=track.sample_rate,
            channels=track.channels,
            file_size=track.file_size,
            mb_trackid=track.mb_trackid,
        )

    except HTTPException:
        raise

    except FileNotFoundError:
        logger.error(f"Beets database not found: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )


@router.get("/{slug}/tracks/{track_id}/stream")
def stream_track(
    slug: str,
    track_id: int,
    request: Request,
    download: bool = Query(False, description="Serve as attachment (direct file download)"),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Stream track audio file.

    Supports HTTP Range requests for seeking. Returns the audio file
    with appropriate Content-Type based on the file format. With
    ``?download=true`` a Content-Disposition attachment header is added so
    the browser saves the file as "Artist - Title.ext".
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        track = beets_service.get_track_by_id(library.database_path, track_id)

        if track is None:
            raise HTTPException(status_code=404, detail="Track not found")

        # Resolve to absolute before any filesystem check — otherwise
        # os.path.exists() resolves a relative beets path against the backend
        # container's CWD ("/app") and 404s every track, which the browser's
        # <audio> element surfaces as the misleading MediaError
        # .SRC_NOT_SUPPORTED ("format not supported").
        absolute_path = resolve_track_path(track.path or "", library.library_path)

        if not absolute_path or not os.path.exists(absolute_path):
            raise HTTPException(status_code=404, detail="Audio file not available")

        # Validate path is within library directory (path traversal prevention)
        if library.library_path and not validate_path_in_library(absolute_path, library.library_path):
            logger.warning(f"Path traversal attempt detected: {absolute_path}")
            raise HTTPException(status_code=404, detail="Audio file not available")

        # Streaming outlives this handler; release the DB connection now so
        # it doesn't sit "idle in transaction" for the whole playback.
        db.close()

        # Get file info
        file_size = os.path.getsize(absolute_path)
        _, ext = os.path.splitext(absolute_path.lower())
        media_type = AUDIO_MIME_TYPES.get(ext, "application/octet-stream")

        # Attachment disposition for direct downloads. RFC 5987 filename* so
        # umlauts in artist/title survive; plain filename as ASCII fallback.
        disposition_headers = {}
        if download:
            base = f"{track.artist} - {track.title}" if track.artist else (track.title or f"track-{track_id}")
            safe = sanitize_filename_component(base, f"track-{track_id}")
            fallback = safe.encode("ascii", "replace").decode("ascii")
            disposition_headers["Content-Disposition"] = (
                f'attachment; filename="{fallback}{ext}"; '
                f"filename*=UTF-8''{quote(safe + ext)}"
            )

        # Parse Range header if present
        range_header = request.headers.get("range")
        range_spec = parse_range_header(range_header, file_size) if range_header else None

        if range_spec:
            # Partial content response (206)
            start, end = range_spec
            content_length = end - start + 1

            headers = {
                "Content-Type": media_type,
                "Content-Length": str(content_length),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
                **disposition_headers,
            }

            return StreamingResponse(
                iter_file(absolute_path, start, end),
                status_code=206,
                headers=headers,
                media_type=media_type,
            )
        else:
            # Full content response (200)
            headers = {
                "Content-Type": media_type,
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
                **disposition_headers,
            }

            return StreamingResponse(
                iter_file(absolute_path),
                status_code=200,
                headers=headers,
                media_type=media_type,
            )

    except HTTPException:
        raise

    except FileNotFoundError:
        logger.error(f"Beets database not found: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )

    except PermissionError:
        logger.error(f"Cannot read beets database: {library.database_path}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error accessing beets database: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )


@router.post("/{slug}/albums/{album_id}/cover", response_model=CoverUploadResponse)
async def upload_album_cover(
    slug: str,
    album_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Upload cover art for an album.

    Accepts JPEG, PNG, GIF, or WebP images. Maximum file size is 10 MB.
    The cover art is saved to the album directory as cover.{ext} and
    the database artpath is updated.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        # Check if album exists
        if not beets_service.album_exists(library.database_path, album_id):
            raise HTTPException(status_code=404, detail="Album not found")

        # Read at most limit+1 bytes so an oversized upload is rejected
        # without buffering the whole body in memory first.
        content = await file.read(MAX_COVER_ART_SIZE + 1)
        if len(content) > MAX_COVER_ART_SIZE:
            raise HTTPException(
                status_code=413,
                detail="File too large. Maximum size: 10 MB",
            )

        # Validate image format by magic bytes
        mime_type = validate_image_format(content)
        if not mime_type:
            raise HTTPException(
                status_code=400,
                detail="Unsupported image format. Accepted formats: JPEG, PNG, GIF, WebP",
            )

        # Get the album folder path
        album_folder = beets_service.get_album_folder_path(library.database_path, album_id)
        if not album_folder:
            raise HTTPException(
                status_code=500,
                detail="Cannot determine album directory",
            )

        # Resolve relative paths against the library root so beets DBs that
        # store relative item paths (e.g. the linuxserver image default) still
        # locate the album folder on disk.
        if not os.path.isabs(album_folder) and library.library_path:
            album_folder = os.path.normpath(os.path.join(library.library_path, album_folder))

        if not os.path.isdir(album_folder):
            logger.error(
                f"Album {album_id} folder does not exist on disk: {album_folder}"
            )
            raise HTTPException(
                status_code=404,
                detail=f"Album folder not found on disk: {album_folder}",
            )

        # Atomic write + stale-variant cleanup (shared with the URL endpoint
        # and the import pipeline). Use the library's configured art_filename
        # so replaces don't leave a second, differently-named cover behind.
        cover_path = write_cover_file(
            album_folder, content, mime_type,
            stem=get_art_filename(library.config_path),
        )

        # Update the database artpath
        beets_service.update_album_artpath(library.database_path, album_id, cover_path)

        # Invalidate Redis cache for this album's cover art
        redis_manager = get_redis_key_manager(get_settings().redis_url)
        redis_manager.set_discovered_cover_art(library.database_path, album_id, cover_path)

        return CoverUploadResponse(
            status="success",
            album_id=album_id,
            cover_path=cover_path,
            message="Cover art updated successfully",
        )

    except HTTPException:
        raise

    except FileNotFoundError as e:
        # The beets DB existence is checked up-front via album_exists(), so a
        # FileNotFoundError here is almost always the cover file's destination
        # folder missing. Surface the actual path rather than masking it as a
        # database error.
        logger.error(f"File not found while writing cover art: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write cover art: {e}",
        )

    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to write cover art file: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except Exception as e:
        logger.error(f"Unexpected error uploading cover art: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload cover art: {str(e)}",
        )


@router.post("/{slug}/albums/{album_id}/cover/url", response_model=CoverUploadResponse)
async def download_album_cover_from_url(
    slug: str,
    album_id: int,
    request_body: CoverUrlRequest,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Download cover art from a URL.

    Downloads an image from the provided URL and saves it as the album's cover art.
    Only HTTP/HTTPS URLs are allowed. Private IP ranges are blocked for security.
    Maximum download size is 10 MB with a 10 second timeout.
    """
    library = get_library_by_slug(db, slug)

    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: database path not configured",
        )

    try:
        # Check if album exists
        if not beets_service.album_exists(library.database_path, album_id):
            raise HTTPException(status_code=404, detail="Album not found")

        # Validate + download through the shared SSRF-guarded fetch: scheme +
        # private-IP checks on the initial URL and on every redirect hop,
        # size-capped streaming download, magic-byte format validation. Runs
        # in a thread so the sync httpx client doesn't block the event loop.
        try:
            content, mime_type = await asyncio.to_thread(
                fetch_cover_bytes, request_body.url
            )
        except CoverDownloadError as e:
            raise HTTPException(status_code=e.status_code, detail=str(e))

        # Get the album folder path
        album_folder = beets_service.get_album_folder_path(library.database_path, album_id)
        if not album_folder:
            raise HTTPException(
                status_code=500,
                detail="Cannot determine album directory",
            )

        # Resolve relative paths against the library root so beets DBs that
        # store relative item paths still locate the album folder on disk.
        if not os.path.isabs(album_folder) and library.library_path:
            album_folder = os.path.normpath(os.path.join(library.library_path, album_folder))

        if not os.path.isdir(album_folder):
            logger.error(
                f"Album {album_id} folder does not exist on disk: {album_folder}"
            )
            raise HTTPException(
                status_code=404,
                detail=f"Album folder not found on disk: {album_folder}",
            )

        # Atomic write + stale-variant cleanup (shared with the upload
        # endpoint and the import pipeline). Use the library's configured
        # art_filename so replaces don't leave a second cover behind.
        cover_path = write_cover_file(
            album_folder, content, mime_type,
            stem=get_art_filename(library.config_path),
        )

        # Update the database artpath
        beets_service.update_album_artpath(library.database_path, album_id, cover_path)

        # Update Redis cache
        redis_manager = get_redis_key_manager(get_settings().redis_url)
        redis_manager.set_discovered_cover_art(library.database_path, album_id, cover_path)

        return CoverUploadResponse(
            status="success",
            album_id=album_id,
            cover_path=cover_path,
            message="Cover art downloaded and saved successfully",
        )

    except HTTPException:
        raise

    except FileNotFoundError as e:
        logger.error(f"File not found while writing cover art: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write cover art: {e}",
        )

    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to write cover art file: permission denied",
        )

    except sqlite3.DatabaseError as e:
        error_msg = str(e).lower()
        if "malformed" in error_msg:
            logger.error(f"Beets database is malformed: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is malformed",
            )
        logger.error(f"Database error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except sqlite3.OperationalError as e:
        error_msg = str(e).lower()
        if "locked" in error_msg:
            logger.error(f"Beets database is locked: {library.database_path}")
            raise HTTPException(
                status_code=500,
                detail="Unable to access beets database: database is locked",
            )
        logger.error(f"Operational error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {str(e)}",
        )

    except Exception as e:
        logger.error(f"Unexpected error downloading cover art: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download cover art: {str(e)}",
        )


@router.post(
    "/{slug}/albums/{album_id}/move",
    response_model=MoveAlbumResponse,
    status_code=202,
)
def move_album_to_library(
    slug: str,
    album_id: int,
    request: MoveAlbumRequest,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Queue a Celery job to move an album from the source library to another library.

    The actual file move and DB sync happens asynchronously; clients should
    poll the activity-monitor stream (or the standard task-event endpoints)
    using the returned ``job_id`` / ``task_event_id`` to track progress.

    Path Parameters:
        slug: Source library slug.
        album_id: Beets album ID in the source library.

    Body:
        target_library_slug: Slug of the destination library.

    Returns:
        202 Accepted with a ``MoveAlbumResponse`` describing the queued job.

    Raises:
        400: target_library_slug is the same as source slug.
        404: Source library, target library, or source album not found.
        409: Target album folder already exists on disk, or another album in
            the source library shares the same folder.
        500: Source/target library is missing database_path or library_path.
    """
    # Late import to avoid pulling Celery into module-import time of the API package.
    from app.tasks.beets_tasks import move_album_task

    source_lib = get_library_by_slug(db, slug)

    target_slug = (request.target_library_slug or "").strip()
    if not target_slug:
        raise HTTPException(status_code=400, detail="target_library_slug is required")
    if target_slug == slug:
        raise HTTPException(
            status_code=400,
            detail="target_library_slug must differ from the source library slug",
        )

    target_lib = db.query(Library).filter(Library.slug == target_slug).first()
    if target_lib is None:
        raise HTTPException(
            status_code=404,
            detail=f"Target library not found: {target_slug}",
        )

    if not source_lib.database_path or not source_lib.library_path:
        raise HTTPException(
            status_code=500,
            detail="Source library has no database_path or library_path configured",
        )
    if not target_lib.database_path or not target_lib.library_path:
        raise HTTPException(
            status_code=500,
            detail="Target library has no database_path or library_path configured",
        )

    # Pre-flight checks against the source DB so we can surface common
    # problems synchronously instead of as a failed background job.
    try:
        if not beets_service.album_exists(source_lib.database_path, album_id):
            raise HTTPException(status_code=404, detail="Album not found in source library")

        tracks = beets_service.get_album_tracks(source_lib.database_path, album_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Source library beets database is missing on disk",
        )
    except sqlite3.DatabaseError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Source library beets database error: {e}",
        )

    if not tracks:
        raise HTTPException(status_code=409, detail="Album has no tracks to move")

    # Compute the prospective target folder so we can fail fast on conflicts.
    source_root = os.path.normpath(source_lib.library_path).rstrip(os.sep)
    target_root = os.path.normpath(target_lib.library_path).rstrip(os.sep)
    sample_path = tracks[0].path or ""
    if not sample_path:
        raise HTTPException(status_code=500, detail="Track 0 has no stored path")
    if os.path.isabs(sample_path):
        normalised_sample = os.path.normpath(sample_path)
        if not normalised_sample.startswith(source_root + os.sep):
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Track path '{sample_path}' is outside source library root "
                    f"'{source_root}'"
                ),
            )
        relative_album_folder = os.path.dirname(
            normalised_sample[len(source_root) + 1 :]
        )
    else:
        relative_album_folder = os.path.dirname(sample_path)
    if not relative_album_folder:
        raise HTTPException(
            status_code=409,
            detail="Album tracks live at the library root — refusing to move",
        )
    target_album_folder = os.path.join(target_root, relative_album_folder)
    if os.path.exists(target_album_folder):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Target already has a folder at '{target_album_folder}'. "
                "Move or rename it before retrying."
            ),
        )

    job_id = str(uuid.uuid4())
    move_album_task.delay(
        job_id=job_id,
        source_library_id=source_lib.id,
        target_library_id=target_lib.id,
        source_album_id=album_id,
    )
    logger.info(
        f"Queued album move job {job_id}: {source_lib.slug}/album/{album_id} "
        f"→ {target_lib.slug}"
    )

    return MoveAlbumResponse(
        status="queued",
        job_id=job_id,
        task_event_id=None,
        source_library_slug=source_lib.slug,
        target_library_slug=target_lib.slug,
        album_id=album_id,
    )


@router.post(
    "/{slug}/albums/{album_id}/convert-wav",
    response_model=ConvertAlbumWavResponse,
    status_code=202,
)
def convert_album_wav(
    slug: str,
    album_id: int,
    request: ConvertAlbumWavRequest,
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Queue an in-place WAV→FLAC conversion for an already-imported album.

    Each WAV track is transcoded losslessly to a sibling ``.flac``, the beets
    item is repointed at the new file (tags written from the DB, stream facts
    refreshed), and — by default — the original WAV is deleted afterwards.
    The job runs asynchronously; poll
    ``/v1/libraries/{slug}/beets/audio-op/{job_id}/status`` for the outcome.

    Raises:
        400: Album has no WAV tracks.
        404: Library or album not found.
        409: Another audio operation is already running for this album.
        500: Library is missing database_path/library_path, or beets DB error.
    """
    # Late import to avoid pulling Celery into module-import time of the API package.
    from app.tasks.beets_tasks import convert_imported_album_task

    library = get_library_by_slug(db, slug)
    if not library.database_path or not library.library_path:
        raise HTTPException(
            status_code=500,
            detail="Library has no database_path or library_path configured",
        )

    try:
        if not beets_service.album_exists(library.database_path, album_id):
            raise HTTPException(status_code=404, detail="Album not found")
        tracks = beets_service.get_album_tracks(library.database_path, album_id)
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Unable to access beets database: file not found",
        )
    except sqlite3.DatabaseError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to access beets database: {e}",
        )

    wav_track_count = sum(
        1 for track in tracks if (track.path or "").lower().endswith(".wav")
    )
    if wav_track_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Album has no WAV tracks to convert",
        )

    redis_manager = get_redis_key_manager(get_settings().redis_url)
    job_id = str(uuid.uuid4())
    # Same lock namespace as the pre-import audio ops, keyed by album id since
    # imported albums are addressed by id, not folder path. TTL slightly above
    # the task's hard time limit so a wedged worker can't hold the album forever.
    lock_token = f"imported-album:{album_id}"
    if not redis_manager.acquire_audio_op_lock(
        library.id, lock_token, job_id, ttl_seconds=1860
    ):
        raise HTTPException(
            status_code=409,
            detail="Another audio operation is already running for this album",
        )

    try:
        # Enqueue as "queued"; the worker flips it to "running" when it starts.
        redis_manager.set_audio_op_status(job_id, status="queued")
        convert_imported_album_task.delay(
            job_id=job_id,
            library_id=library.id,
            album_id=album_id,
            delete_originals=request.delete_originals,
        )
    except Exception as e:
        redis_manager.release_audio_op_lock(library.id, lock_token)
        logger.error(f"Failed to dispatch imported-album WAV conversion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start conversion: {e}")

    logger.info(
        f"Queued in-place WAV→FLAC conversion {job_id}: "
        f"{library.slug}/album/{album_id} ({wav_track_count} WAV tracks)"
    )
    return ConvertAlbumWavResponse(
        job_id=job_id,
        album_id=album_id,
        wav_track_count=wav_track_count,
        message=f"WAV→FLAC conversion queued for {wav_track_count} track(s)",
    )


@router.post("/{slug}/albums/backfill-cover-art", status_code=202)
def backfill_album_cover_art(slug: str, db: Session = Depends(get_db)):
    """Queue a background pass that fills in missing cover art for this library.

    For every album currently lacking a valid on-disk cover, it materialises a
    discoverable one (an in-folder image, a scene ``00-*`` file, or art embedded
    in the tracks) and points ``artpath`` at it — so previously-imported albums
    show their covers in the grid without a re-import. Idempotent.

    Returns 202 with the Celery ``task_id``.
    """
    library = get_library_by_slug(db, slug)
    if not library.database_path:
        raise HTTPException(
            status_code=500,
            detail="Library has no beets database configured",
        )

    # Late import to keep Celery out of the API package's import time.
    from app.tasks.beets_tasks import backfill_cover_art_task

    task = backfill_cover_art_task.delay(library.id)
    logger.info(f"Queued cover-art backfill for library {library.slug}: task {task.id}")
    return {"status": "queued", "task_id": task.id, "library_id": library.id}


def _prune_empty_parent_dirs(start_folder: str, library_root: str) -> None:
    """Remove now-empty parent dirs above a removed/moved album folder.

    Walks upward from the album folder's parent, deleting empty directories
    (leftover Artist/ folders etc.) until it hits a non-empty dir or the
    library-root boundary. Best-effort: logs and stops on the first OSError.
    Never deletes the library root itself.

    Each candidate is re-checked after symlink resolution before deletion: a
    symlinked directory is never followed, and a parent whose real path
    escapes the library root is left untouched — so a stray symlink inside
    the tree can't make ``rmdir`` walk outside it.
    """
    root = os.path.normpath(library_root).rstrip(os.sep)
    real_root = os.path.realpath(root)
    try:
        parent = os.path.dirname(start_folder)
        while parent and parent != root and parent.startswith(root + os.sep):
            # Defense in depth: don't follow a symlinked dir, and confirm the
            # resolved path is still inside the library root before removing it.
            if os.path.islink(parent):
                break
            real_parent = os.path.realpath(parent)
            if real_parent == real_root or not real_parent.startswith(real_root + os.sep):
                break
            if os.listdir(parent):
                break
            os.rmdir(parent)
            parent = os.path.dirname(parent)
    except OSError as e:
        logger.warning(f"Error pruning empty parent dirs above {start_folder}: {e}")


@router.delete("/{slug}/albums/{album_id}", response_model=DeleteAlbumResponse)
def delete_album(
    slug: str,
    album_id: int,
    mode: DeleteAlbumMode = Query(
        ...,
        description=(
            "delete_files = remove the beets entry AND erase the folder from "
            "disk; move_to_import = remove the beets entry but move the folder "
            "back into the library's import staging area for re-import; "
            "detach = remove only the beets entry, never touch disk (the only "
            "mode that works on a duplicate row sharing its folder with "
            "another album)."
        ),
    ),
    db: Session = Depends(get_db),
    beets_service: BeetsLibraryService = Depends(get_beets_library_service),
):
    """Delete a single album from a library (synchronous).

    The beets DB rows are removed in every mode; ``mode`` only decides what
    happens to the audio files on disk. Files are only touched after the
    album folder is validated to sit strictly below the library root and to
    contain no other album's tracks (mixed-folder guard). ``detach`` skips
    the file op — and therefore all folder guards — entirely: it is the
    escape hatch for duplicate rows sharing one folder, which the guarded
    modes refuse with 409 (each row guards the folder against its sibling).

    Ordering note: the DB rows are removed *before* the file op (consistent
    with delete_library) — orphaned files are recoverable, dangling DB rows
    are user-visible breakage. ``move_to_import`` uses ``shutil.move``, which
    is a non-atomic copy+delete when the library and import roots live on
    different filesystems; a failure mid-op surfaces a 500 naming the folder.

    Raises:
        404: Album not found in the library.
        409: (file modes only) Album spans multiple folders / lives at the
            library root / shares its folder with another album / its folder
            is missing on disk, or (move mode) the import destination already
            exists.
        400: The resolved folder escapes the library root after symlink
            resolution.
        500: Library missing path config, beets DB missing/corrupt, or the
            file operation failed after the DB rows were removed.
    """
    library = get_library_by_slug(db, slug)
    if not library.database_path or not library.library_path:
        raise HTTPException(
            status_code=500,
            detail="Library has no database_path or library_path configured",
        )
    if mode == DeleteAlbumMode.move_to_import and not library.import_path:
        raise HTTPException(
            status_code=500,
            detail="Library has no import_path configured; cannot move to import",
        )

    library_root = os.path.normpath(library.library_path).rstrip(os.sep)

    # Row-only removal: no file op, so none of the folder guards apply — they
    # exist to protect a disk operation this mode never performs. Deliberately
    # tolerant of on-disk state (folder shared, missing, or spanning multiple
    # dirs): detach is the cleanup path for rows whose folder situation the
    # guarded modes refuse.
    if mode == DeleteAlbumMode.detach:
        try:
            if not beets_service.album_exists(library.database_path, album_id):
                raise HTTPException(
                    status_code=404, detail="Album not found in library"
                )
            beets_service.delete_album(library.database_path, album_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=500, detail="Library beets database is missing on disk"
            )
        except sqlite3.DatabaseError as e:
            raise HTTPException(
                status_code=500, detail=f"Library beets database error: {e}"
            )
        logger.info(
            f"Detached album {album_id} from {library.slug} "
            f"(DB rows removed, files untouched)"
        )
        return DeleteAlbumResponse(
            status="deleted",
            album_id=album_id,
            mode=mode,
            files_deleted=False,
            relocated_to=None,
        )

    # Resolve + guard the album folder against the source DB BEFORE deleting
    # any rows — the mixed-folder guard needs the DB intact.
    try:
        if not beets_service.album_exists(library.database_path, album_id):
            raise HTTPException(status_code=404, detail="Album not found in library")
        album_folder = beets_service.resolve_album_folder(
            library.database_path, album_id, library_root
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500, detail="Library beets database is missing on disk"
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except sqlite3.DatabaseError as e:
        raise HTTPException(
            status_code=500, detail=f"Library beets database error: {e}"
        )

    # Defense in depth: the resolved folder must stay within the library root
    # even after symlink resolution before we ever rmtree/move it.
    real_root = os.path.realpath(library_root)
    real_folder = os.path.realpath(album_folder)
    if real_folder == real_root or not real_folder.startswith(real_root + os.sep):
        raise HTTPException(
            status_code=400,
            detail="Album folder resolves outside the library root — refusing",
        )

    if not os.path.isdir(album_folder):
        raise HTTPException(
            status_code=409, detail=f"Album folder is missing on disk: {album_folder}"
        )

    # For move-to-import, fail fast on a destination conflict before the DB
    # rows are removed.
    dest_folder: Optional[str] = None
    if mode == DeleteAlbumMode.move_to_import:
        import_root = os.path.normpath(library.import_path).rstrip(os.sep)
        relative = os.path.relpath(album_folder, library_root)
        dest_folder = os.path.join(import_root, relative)
        if os.path.exists(dest_folder):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Import folder already has '{dest_folder}'. Move or rename "
                    "it before retrying."
                ),
            )

    # Remove the beets DB rows first — matches delete_library ordering: the DB
    # is the source of truth the UI reads, so orphaned files (recoverable) are
    # preferable to dangling rows (user-visible breakage).
    beets_service.delete_album(library.database_path, album_id)

    files_deleted = False
    relocated_to: Optional[str] = None
    try:
        if mode == DeleteAlbumMode.delete_files:
            shutil.rmtree(album_folder)
            files_deleted = True
        else:
            os.makedirs(os.path.dirname(dest_folder), exist_ok=True)
            shutil.move(album_folder, dest_folder)
            relocated_to = dest_folder
        _prune_empty_parent_dirs(album_folder, library_root)
    except OSError as e:
        # The DB rows are already gone (intentional ordering), so log the exact
        # folder at error level and echo it back — an operator needs the path
        # to clean up any files orphaned by the half-completed op.
        logger.error(
            f"Album {album_id} DB rows removed but file op failed "
            f"(mode={mode.value}, folder={album_folder}): {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                f"Album removed from database, but the file operation failed for "
                f"'{album_folder}': {e}. The files may need manual cleanup."
            ),
        )

    logger.info(
        f"Deleted album {album_id} from {library.slug} (mode={mode.value}, "
        f"folder={album_folder}, relocated_to={relocated_to})"
    )
    return DeleteAlbumResponse(
        status="deleted",
        album_id=album_id,
        mode=mode,
        files_deleted=files_deleted,
        relocated_to=relocated_to,
    )
