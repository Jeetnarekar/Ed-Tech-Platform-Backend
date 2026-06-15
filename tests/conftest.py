import asyncio
import os
import pytest
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.app.core.config import settings
from src.app.models import Base
from src.app.main import app
from src.app.api import deps

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

# Override settings for Testing environment
settings.ENV = "testing"
settings.DEBUG = False
settings.DATABASE_URL = "sqlite+aiosqlite:///test_db.sqlite"

# Use DB index 1 for testing Redis
settings.REDIS_DB = 1
settings.REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

# Test database engine
test_engine = create_async_engine(settings.DATABASE_URL, poolclass=None)
TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Provides a single event loop per testing session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """
    Creates all database tables before test session, and drops them after.
    Provides schema isolation for testing.
    """
    async with test_engine.begin() as conn:
        # Recreate schema
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    
    # Cleanup SQLite DB file
    db_file = "test_db.sqlite"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a clean database session per test, executing inside a rollback transaction
    to keep test runs completely isolated and side-effect free.
    """
    async with TestAsyncSessionLocal() as session:
        yield session
        # Rollback all database modifications made during the test
        await session.rollback()


# Simple Mock Redis Client for testing if Redis server is not reachable
class MockRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        return True

    async def delete(self, key: str):
        if key in self.store:
            del self.store[key]
        return 1

    async def ping(self):
        return True

    async def close(self):
        pass


@pytest.fixture
async def mock_redis() -> AsyncGenerator[MockRedis, None]:
    """Yields a mock redis client to isolate cache states."""
    yield MockRedis()


@pytest.fixture
async def client(db_session: AsyncSession, mock_redis: MockRedis) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX AsyncClient fixture configured to hit our FastAPI application.
    Overrides FastAPI dependencies for DB and Redis to use our test fixtures.
    """
    # Override dependencies
    async def override_db():
        yield db_session

    async def override_redis():
        yield mock_redis

    app.dependency_overrides[deps.get_async_db] = override_db
    app.dependency_overrides[deps.get_redis] = override_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.clear()
