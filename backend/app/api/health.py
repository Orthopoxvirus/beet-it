from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
import redis
from app.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "beets-web-manager"}


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Readiness check - verifies database and redis connections."""
    checks = {"database": False, "redis": False}

    # Check database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        checks["database"] = str(e)

    # Check redis
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        checks["redis"] = True
    except Exception as e:
        checks["redis"] = str(e)

    all_healthy = all(v is True for v in checks.values())

    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks
    }
