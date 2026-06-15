import time
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.api import deps
from src.app.core.logging import logger

router = APIRouter()


@router.get("/health", summary="Health Check")
async def health_check(
    db: AsyncSession = Depends(deps.get_async_db),
    redis: Redis = Depends(deps.get_redis),
):
    """
    Service health check endpoint.
    Verifies operational status of external dependencies: PostgreSQL database and Redis caching.
    """
    start_time = time.perf_counter()
    
    db_ok = False
    redis_ok = False
    details = {}

    # Check Database Connection
    try:
        await db.execute(select(1))
        db_ok = True
        details["database"] = "healthy"
    except Exception as err:
        logger.error("Health check database failure", error=str(err))
        details["database"] = f"unhealthy: {str(err)}"

    # Check Redis Connection
    try:
        await redis.ping()
        redis_ok = True
        details["redis"] = "healthy"
    except Exception as err:
        logger.error("Health check redis failure", error=str(err))
        details["redis"] = f"unhealthy: {str(err)}"

    duration = time.perf_counter() - start_time
    is_healthy = db_ok and redis_ok
    status_msg = "healthy" if is_healthy else "unhealthy"

    return {
        "status": status_msg,
        "timestamp": time.time(),
        "duration_seconds": round(duration, 4),
        "components": details,
    }
