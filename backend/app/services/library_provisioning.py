"""Library provisioning service for managing beets library resources."""

import os
import shutil
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

import yaml
from slugify import slugify

from app.config import get_settings
from app.schemas.beets_config import DEFAULT_ITEM_FIELDS, DEFAULT_PATH_TEMPLATES

logger = logging.getLogger(__name__)

# Timeout for beets verification command in seconds
VERIFICATION_TIMEOUT_SECONDS = 30


@dataclass
class LibraryPaths:
    """Container for all paths associated with a library."""
    slug: str
    config_path: str
    database_path: str
    library_path: str
    import_path: str


@dataclass
class VerificationResult:
    """Result of beets configuration verification."""
    success: bool
    config_path: Optional[str] = None
    error: Optional[str] = None
    timed_out: bool = False


@dataclass
class ProvisioningResult:
    """Result of library provisioning including paths and verification status."""
    paths: LibraryPaths
    verification: VerificationResult


def _parse_config_path(stdout: str) -> Optional[str]:
    """Extract the config path from beets config -p output.

    The beets 'config -p' command outputs the path to the config file(s) being used.
    This function extracts and returns the first valid config path from the output.

    Args:
        stdout: The stdout output from the beets config -p command.

    Returns:
        The extracted config file path, or None if not found.
    """
    if not stdout:
        return None

    # The output may have multiple lines; take the first non-empty line
    lines = stdout.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line and line.endswith('.yaml'):
            return line
    # If no .yaml file found, return the first non-empty line
    for line in lines:
        line = line.strip()
        if line:
            return line
    return None


def verify_library_config(config_path: str) -> VerificationResult:
    """Verify a beets library configuration file by executing beets config -p.

    This function runs the beets CLI with the specified config file to verify
    the configuration is valid. As a side effect, beets will initialize the
    SQLite database if it doesn't exist.

    Args:
        config_path: The absolute path to the beets config file to verify.

    Returns:
        VerificationResult containing success status, config path, error message,
        and timeout flag.
    """
    logger.info(f"Verifying library config: {config_path}")

    cmd = ["python", "-m", "beets", "-c", config_path, "config", "-p"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=False,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
        )

        if result.returncode == 0:
            parsed_path = _parse_config_path(result.stdout)
            logger.info(f"Library config verified: {config_path}")
            return VerificationResult(
                success=True,
                config_path=parsed_path or config_path,
                error=None,
                timed_out=False,
            )
        else:
            error_msg = result.stderr.strip() if result.stderr else f"Command exited with code {result.returncode}"
            logger.warning(f"Library config verification failed: {error_msg}")
            return VerificationResult(
                success=False,
                config_path=None,
                error=error_msg,
                timed_out=False,
            )

    except subprocess.TimeoutExpired:
        logger.warning(f"Library config verification timed out after {VERIFICATION_TIMEOUT_SECONDS}s")
        return VerificationResult(
            success=False,
            config_path=None,
            error=None,
            timed_out=True,
        )

    except FileNotFoundError as e:
        error_msg = "Beets executable not found. Ensure beets is installed."
        logger.error(f"Failed to execute beets verification: {e}")
        return VerificationResult(
            success=False,
            config_path=None,
            error=error_msg,
            timed_out=False,
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to execute beets verification: {e}")
        return VerificationResult(
            success=False,
            config_path=None,
            error=error_msg,
            timed_out=False,
        )


class LibraryProvisioningService:
    """Service for provisioning and managing beets library resources.

    This service handles:
    - Slug generation from library names
    - Path generation for config, database, library, and import directories
    - Beets config YAML file generation
    - Directory creation
    - Resource cleanup on deletion
    """

    def __init__(self, settings=None):
        """Initialize the provisioning service.

        Args:
            settings: Application settings. If None, uses default settings.
        """
        self.settings = settings or get_settings()

    def generate_slug(self, name: str) -> str:
        """Generate a filesystem-safe slug from a library name.

        Uses python-slugify to handle unicode transliteration and special characters.

        Args:
            name: The library display name.

        Returns:
            A lowercase, hyphen-separated slug suitable for filesystem paths.

        Examples:
            "Jazz Collection!" -> "jazz-collection"
            "My Awesome Library" -> "my-awesome-library"
            "Musik fur Kinder" -> "musik-fur-kinder"
        """
        return slugify(name, lowercase=True, separator="-")

    def generate_paths(self, slug: str) -> LibraryPaths:
        """Generate all paths for a library based on its slug.

        Args:
            slug: The filesystem-safe slug for the library.

        Returns:
            LibraryPaths containing all path information.
        """
        return LibraryPaths(
            slug=slug,
            config_path=os.path.join(self.settings.config_path, f"{slug}.yaml"),
            database_path=os.path.join(self.settings.databases_path, f"{slug}.db"),
            library_path=os.path.join(self.settings.libraries_path, f"{slug}") + "/",
            import_path=os.path.join(self.settings.import_path, f"{slug}") + "/",
        )

    def check_slug_collision(self, slug: str) -> tuple[bool, Optional[str]]:
        """Check if a slug would collide with existing filesystem resources.

        Checks for existing config file, database file, library directory, or import directory.

        Args:
            slug: The slug to check for collisions.

        Returns:
            Tuple of (has_collision, resource_path).
            If has_collision is True, resource_path contains the path of the existing resource.
        """
        paths = self.generate_paths(slug)

        # Check each path in order of importance
        if os.path.exists(paths.config_path):
            return True, paths.config_path
        if os.path.exists(paths.database_path):
            return True, paths.database_path
        if os.path.exists(paths.library_path.rstrip("/")):
            return True, paths.library_path
        if os.path.exists(paths.import_path.rstrip("/")):
            return True, paths.import_path

        return False, None

    def generate_beets_config(self, paths: LibraryPaths) -> str:
        """Generate beets configuration YAML content.

        Args:
            paths: LibraryPaths containing the paths to use in the config.

        Returns:
            YAML string for the beets configuration file.
        """
        config = {
            "directory": paths.library_path.rstrip("/"),
            "library": paths.database_path,
            "import": {
                "default_action": "write",
                "move": False,
                "copy": True,
            },
            # Disc-aware path templates: multi-disc releases repeat track
            # numbers per disc, so without the $disc prefix beets would render
            # colliding paths and overwrite files across discs. $multidisc is
            # computed by the bundled `inline` plugin; single-disc paths are
            # unaffected.
            "plugins": ["inline"],
            "item_fields": DEFAULT_ITEM_FIELDS.copy(),
            "paths": {
                "default": DEFAULT_PATH_TEMPLATES["default"],
                "singleton": DEFAULT_PATH_TEMPLATES["singleton"],
                "comp": DEFAULT_PATH_TEMPLATES["comp"],
                "albumtype:soundtrack": DEFAULT_PATH_TEMPLATES["albumtype_soundtrack"],
            },
        }
        return yaml.dump(config, default_flow_style=False, sort_keys=False)

    def create_directories(self, paths: LibraryPaths) -> None:
        """Create the library and import directories.

        Creates the directories with exist_ok=True so it's idempotent.
        Also ensures the databases directory exists.

        Args:
            paths: LibraryPaths containing the directories to create.

        Raises:
            OSError: If directory creation fails.
        """
        # Ensure databases directory exists
        os.makedirs(self.settings.databases_path, exist_ok=True)

        # Create library directory
        os.makedirs(paths.library_path.rstrip("/"), exist_ok=True)

        # Create import directory
        os.makedirs(paths.import_path.rstrip("/"), exist_ok=True)

        logger.info(f"Created directories for library: {paths.library_path}, {paths.import_path}")

    def write_config_file(self, paths: LibraryPaths) -> None:
        """Write the beets configuration file.

        Args:
            paths: LibraryPaths containing the config path and other settings.

        Raises:
            OSError: If file writing fails.
        """
        config_content = self.generate_beets_config(paths)

        # Ensure config directory exists
        os.makedirs(os.path.dirname(paths.config_path), exist_ok=True)

        with open(paths.config_path, "w") as f:
            f.write(config_content)

        logger.info(f"Created beets config file: {paths.config_path}")

    def generate_unique_slug(self, base_slug: str, existing_slugs: Optional[set] = None) -> str:
        """Generate a unique slug by appending numeric suffix if needed.

        Checks both filesystem and provided existing slugs set for collisions.

        Args:
            base_slug: The base slug to make unique.
            existing_slugs: Optional set of existing slugs from database.

        Returns:
            A unique slug (possibly with numeric suffix like "my-library-2").
        """
        slug = base_slug
        suffix = 2

        while True:
            # Check filesystem collision
            has_fs_collision, _ = self.check_slug_collision(slug)

            # Check database collision
            has_db_collision = existing_slugs is not None and slug in existing_slugs

            if not has_fs_collision and not has_db_collision:
                return slug

            slug = f"{base_slug}-{suffix}"
            suffix += 1

    def provision_library(
        self,
        name: str,
        user_slug: Optional[str] = None,
        existing_slugs: Optional[set] = None,
    ) -> ProvisioningResult:
        """Provision all resources for a new library.

        This method performs filesystem operations BEFORE the database commit
        to make cleanup easier on failure. The order is:
        1. Use provided slug or generate slug from name
        2. Check for filesystem collisions (for user-provided slug, raise error;
           for auto-generated slug, append numeric suffix)
        3. Generate all paths
        4. Create directories
        5. Write config file
        6. Verify the config file by running beets config -p

        If any step fails (except verification), cleanup_on_failure should be called.
        Verification failures do not fail the provisioning; they are reported in the result.

        Args:
            name: The display name for the library.
            user_slug: Optional user-provided slug. If None, auto-generate from name.
            existing_slugs: Optional set of existing slugs from database for collision checking.

        Returns:
            ProvisioningResult with paths and verification status.

        Raises:
            ValueError: If user-provided slug collides with existing filesystem resources
                       or if auto-generated slug cannot be made unique.
            OSError: If filesystem operations fail.
        """
        if user_slug:
            # User provided a slug - check for filesystem collision (strict)
            slug = user_slug
            has_collision, collision_path = self.check_slug_collision(slug)
            if has_collision:
                raise ValueError(
                    f"Slug '{slug}' already exists on the filesystem. "
                    f"Choose a different slug. (Conflicting resource: {collision_path})"
                )
        else:
            # Auto-generate slug from name with collision handling
            base_slug = self.generate_slug(name)
            slug = self.generate_unique_slug(base_slug, existing_slugs)

        paths = self.generate_paths(slug)

        # Create filesystem resources
        # Order: directories first, then config file
        self.create_directories(paths)
        self.write_config_file(paths)

        # Verify the config file (this never raises, always returns a result)
        verification = verify_library_config(paths.config_path)

        if verification.success:
            logger.info(f"Successfully provisioned and verified library '{name}' with slug '{slug}'")
        else:
            if verification.timed_out:
                logger.warning(
                    f"Library '{name}' provisioned but verification timed out after {VERIFICATION_TIMEOUT_SECONDS}s"
                )
            else:
                logger.warning(
                    f"Library '{name}' provisioned but verification failed: {verification.error}"
                )

        return ProvisioningResult(paths=paths, verification=verification)

    def cleanup_on_failure(self, paths: LibraryPaths) -> None:
        """Clean up filesystem resources after a failed provisioning attempt.

        Removes any resources that were created during a failed provision_library call.
        Errors during cleanup are logged but don't raise exceptions.

        Args:
            paths: LibraryPaths containing the paths to clean up.
        """
        # Remove config file
        try:
            if os.path.exists(paths.config_path):
                os.remove(paths.config_path)
                logger.info(f"Cleaned up config file: {paths.config_path}")
        except OSError as e:
            logger.error(f"Failed to clean up config file {paths.config_path}: {e}")

        # Remove library directory (if empty or newly created)
        try:
            library_dir = paths.library_path.rstrip("/")
            if os.path.exists(library_dir) and not os.listdir(library_dir):
                os.rmdir(library_dir)
                logger.info(f"Cleaned up library directory: {library_dir}")
        except OSError as e:
            logger.error(f"Failed to clean up library directory {paths.library_path}: {e}")

        # Remove import directory (if empty or newly created)
        try:
            import_dir = paths.import_path.rstrip("/")
            if os.path.exists(import_dir) and not os.listdir(import_dir):
                os.rmdir(import_dir)
                logger.info(f"Cleaned up import directory: {import_dir}")
        except OSError as e:
            logger.error(f"Failed to clean up import directory {paths.import_path}: {e}")

    def cleanup_resources(
        self,
        config_path: Optional[str],
        database_path: Optional[str],
        library_path: Optional[str],
        import_path: Optional[str],
        keep_config: bool = True,
        keep_database: bool = True,
        keep_folders: bool = True,
    ) -> dict[str, bool]:
        """Selectively clean up library resources.

        This method is used when deleting a library to optionally remove
        associated filesystem resources.

        Args:
            config_path: Path to the beets config file.
            database_path: Path to the beets database file.
            library_path: Path to the library directory.
            import_path: Path to the import directory.
            keep_config: If False, delete the config file.
            keep_database: If False, delete the database file.
            keep_folders: If False, delete library and import directories.

        Returns:
            Dictionary indicating which resource types were deleted.
        """
        result = {
            "config": False,
            "database": False,
            "folders": False,
        }

        # Delete config file if requested
        if not keep_config and config_path:
            try:
                if os.path.exists(config_path):
                    os.remove(config_path)
                    result["config"] = True
                    logger.info(f"Deleted config file: {config_path}")
            except OSError as e:
                logger.error(f"Failed to delete config file {config_path}: {e}")

        # Delete database file if requested
        if not keep_database and database_path:
            try:
                if os.path.exists(database_path):
                    os.remove(database_path)
                    result["database"] = True
                    logger.info(f"Deleted database file: {database_path}")
            except OSError as e:
                logger.error(f"Failed to delete database file {database_path}: {e}")

        # Delete directories if requested
        if not keep_folders:
            # Delete library directory
            if library_path:
                try:
                    lib_dir = library_path.rstrip("/")
                    if os.path.exists(lib_dir):
                        shutil.rmtree(lib_dir)
                        result["folders"] = True
                        logger.info(f"Deleted library directory: {lib_dir}")
                except OSError as e:
                    logger.error(f"Failed to delete library directory {library_path}: {e}")

            # Delete import directory
            if import_path:
                try:
                    imp_dir = import_path.rstrip("/")
                    if os.path.exists(imp_dir):
                        shutil.rmtree(imp_dir)
                        result["folders"] = True
                        logger.info(f"Deleted import directory: {imp_dir}")
                except OSError as e:
                    logger.error(f"Failed to delete import directory {import_path}: {e}")

        return result

    def get_path_status(
        self,
        directory_path: Optional[str],
        database_path: Optional[str],
    ) -> Tuple[bool, bool]:
        """Check existence status of library paths.

        Args:
            directory_path: The library directory path from beets config.
            database_path: The database file path from beets config.

        Returns:
            Tuple of (directory_exists, database_exists).
        """
        directory_exists = bool(directory_path and os.path.isdir(directory_path))
        database_exists = bool(database_path and os.path.isfile(database_path))
        return directory_exists, database_exists

    def validate_path_boundaries(self, path: str) -> bool:
        """Validate that a path is within allowed mount boundaries.

        Checks that the given path is within one of the allowed base paths
        (libraries_path or databases_path) to prevent unauthorized filesystem access.

        Args:
            path: The path to validate.

        Returns:
            True if path is within allowed boundaries.

        Raises:
            ValueError: If path is outside allowed boundaries.
        """
        # Normalize the path to resolve symlinks and relative components
        normalized_path = os.path.normpath(os.path.abspath(path))

        # Check against allowed paths from settings
        allowed_paths = [
            self.settings.libraries_path,
            self.settings.databases_path,
        ]

        for allowed in allowed_paths:
            normalized_allowed = os.path.normpath(os.path.abspath(allowed))
            # Use os.path.commonpath to properly check path containment
            try:
                common = os.path.commonpath([normalized_path, normalized_allowed])
                if common == normalized_allowed:
                    return True
            except ValueError:
                # Paths are on different drives (Windows) - skip this check
                continue

        raise ValueError(f"Path '{path}' is outside allowed mount boundaries")

    def initialize_library_resources(
        self,
        config_path: str,
        directory_path: str,
        database_path: str,
    ) -> Tuple[bool, bool]:
        """Initialize library resources (directory and database).

        Creates the library directory if missing and runs `beet config -p`
        to initialize the beets database. This operation is idempotent -
        existing resources are not modified.

        Args:
            config_path: Path to the beets config file.
            directory_path: The library directory path.
            database_path: The database file path.

        Returns:
            Tuple of (directory_created, database_initialized).

        Raises:
            ValueError: If paths are outside allowed boundaries.
            OSError: If directory creation fails.
            RuntimeError: If beets initialization fails or times out.
        """
        # Validate paths are within boundaries
        self.validate_path_boundaries(directory_path)
        self.validate_path_boundaries(database_path)

        directory_created = False
        database_initialized = False

        # Create directory if it doesn't exist
        if not os.path.isdir(directory_path):
            os.makedirs(directory_path, exist_ok=True)
            directory_created = True
            logger.info(f"Created library directory: {directory_path}")

        # Ensure databases directory exists
        db_dir = os.path.dirname(database_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        # Initialize database via beet config -p if it doesn't exist
        if not os.path.isfile(database_path):
            result = verify_library_config(config_path)

            if result.timed_out:
                raise RuntimeError(
                    f"Initialization timed out after {VERIFICATION_TIMEOUT_SECONDS}s"
                )

            if not result.success:
                raise RuntimeError(f"Database initialization failed: {result.error}")

            database_initialized = True
            logger.info(f"Initialized beets database: {database_path}")

        return directory_created, database_initialized
