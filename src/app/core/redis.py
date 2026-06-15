from typing import AsyncGenerator
from redis.asyncio import ConnectionPool, Redis
from src.app.core.config import settings
from src.app.core.logging import logger

# Global pool and client references
redis_pool: ConnectionPool | None = None
redis_client: Redis | None = None


def init_redis() -> None:
    """Initializes the Redis connection pool."""
    global redis_pool, redis_client
    logger.info("Initializing Redis connection pool...", url=settings.REDIS_URL)
    
    redis_pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,  # Automatically decode bytes to str
        max_connections=50,
    )
    redis_client = Redis(connection_pool=redis_pool)


async def close_redis() -> None:
    """Closes the Redis connection pool."""
    global redis_pool, redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis client connection closed.")
    if redis_pool:
        await redis_pool.disconnect()
        logger.info("Redis connection pool disconnected.")


async def get_redis_client() -> AsyncGenerator[Redis, None]:
    """Dependency injection helper to yield active Redis client."""
    if redis_client is None:
        raise RuntimeError("Redis connection has not been initialized.")
    yield redis_client
