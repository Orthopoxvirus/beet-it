"""API routes package."""

from app.api.routes.scan import router as scan_router
from app.api.routes.batch_tag import router as batch_tag_router
from app.api.routes.upload import router as upload_router
from app.api.routes.settings import router as settings_router
from app.api.routes.beets_autotag import router as beets_autotag_router
from app.api.routes.beets_autotag import library_settings_router
from app.api.routes.activity import router as activity_router
from app.api.routes.library_items import router as library_items_router
from app.api.routes.downloads import router as downloads_router
from app.api.routes.titles import router as titles_router

__all__ = [
    "scan_router",
    "batch_tag_router",
    "upload_router",
    "settings_router",
    "beets_autotag_router",
    "library_settings_router",
    "activity_router",
    "library_items_router",
    "downloads_router",
    "titles_router",
]
