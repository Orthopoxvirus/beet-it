import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.middleware import BasicAuthMiddleware
from app.api import health, libraries, config, filesystem, maintenance
from app.api.routes import scan_router, batch_tag_router, upload_router, settings_router, beets_autotag_router, library_settings_router, activity_router, library_items_router, downloads_router, titles_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="A web-based UI for managing music libraries with beets",
    version="0.2.1",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS (must be added first so it handles preflight requests before auth)
origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timing middleware to log request durations
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} completed in {duration:.2f}s")
    return response

# Configure Basic Authentication middleware
# Note: Middleware is executed in reverse order of addition,
# so CORS (added first) will run before BasicAuth (added second)
app.add_middleware(
    BasicAuthMiddleware,
    username=settings.basic_auth_user,
    password=settings.basic_auth_password,
)

# Include routers
app.include_router(health.router)
app.include_router(libraries.router, prefix="/api/v1")
app.include_router(config.router, prefix="/api/v1")
app.include_router(maintenance.router, prefix="/api/v1")
app.include_router(filesystem.router, prefix="/api/v1")
app.include_router(scan_router, prefix="/api")
app.include_router(batch_tag_router, prefix="/api/v1")
app.include_router(upload_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(beets_autotag_router, prefix="/api/v1")
app.include_router(library_settings_router, prefix="/api/v1")
app.include_router(activity_router, prefix="/api/v1")
app.include_router(library_items_router, prefix="/api/v1")
app.include_router(downloads_router, prefix="/api/v1")
app.include_router(titles_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """Log application startup and authentication status."""
    if settings.is_auth_enabled:
        logger.info("Basic authentication is ENABLED. All endpoints require valid credentials.")
    else:
        logger.info("Basic authentication is DISABLED. All endpoints are publicly accessible.")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "0.2.1",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
