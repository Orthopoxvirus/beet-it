import logging
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Beets Web Manager"
    debug: bool = False

    # Database
    database_url: str = "postgresql://beets:beets@postgres:5432/beets_db"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Celery
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"

    # Security
    secret_key: str = "change-me-in-production"

    # Basic Authentication (optional)
    basic_auth_user: Optional[str] = None
    basic_auth_password: Optional[str] = None

    # CORS
    cors_origins: str = "*"

    # Volume paths
    libraries_path: str = "/data/libraries"
    import_path: str = "/data/import"
    upload_path: str = "/data/upload"
    config_path: str = "/config"
    databases_path: str = "/data/databases"
    downloads_path: str = "/data/downloads"

    # Import Folder Watcher Configuration
    enable_import_watchers: bool = True
    scan_debounce_seconds: int = 30
    scan_timeout_seconds: int = 3600

    # Analysis Queue Configuration
    max_concurrent_analyses_per_library: int = 2

    # BPM analysis (maintenance backfill): number of parallel `beet autobpm`
    # subprocesses. 0 = auto (half the CPU cores visible to the container,
    # min 1). librosa is CPU-bound and single-threaded per process, so
    # parallel chunks scale nearly linearly.
    bpm_analysis_workers: int = 0

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def is_auth_enabled(self) -> bool:
        """Check if basic auth is enabled (both credentials must be non-empty)."""
        return bool(self.basic_auth_user and self.basic_auth_password)

    def validate_auth_config(self) -> None:
        """Validate auth configuration and log warnings for incomplete config."""
        has_user = bool(self.basic_auth_user)
        has_password = bool(self.basic_auth_password)

        if has_user and not has_password:
            logger.warning(
                "BASIC_AUTH_USER is set but BASIC_AUTH_PASSWORD is not. "
                "Basic authentication is DISABLED. Set both to enable auth."
            )
        elif has_password and not has_user:
            logger.warning(
                "BASIC_AUTH_PASSWORD is set but BASIC_AUTH_USER is not. "
                "Basic authentication is DISABLED. Set both to enable auth."
            )


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_auth_config()
    return settings
