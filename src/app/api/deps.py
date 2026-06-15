import uuid
from typing import AsyncGenerator
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.core.config import settings
from src.app.core.database import AsyncSessionLocal
from src.app.core.exceptions import AuthenticationException, NotFoundException
from src.app.core.middlewares import tenant_context
from src.app.core.redis import get_redis_client
from src.app.models.tenant import Tenant
from src.app.schemas.auth import TokenPayload
from src.app.services.tenant import tenant_service

# Bearer token extractor
reusable_oauth2 = HTTPBearer(auto_error=False)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to yield an async database session per request.
    Handles transaction commits and automatically rolls back in case of errors.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # Automatically commit pending database modifications at request end
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    Dependency to yield the active global Redis client.
    """
    async for client in get_redis_client():
        yield client


async def get_current_tenant(
    db: AsyncSession = Depends(get_async_db),
    redis: Redis = Depends(get_redis),
) -> Tenant:
    """
    Dependency to resolve and return the active Tenant/Institute.
    Extracts the tenant identifier from the request state (configured by TenantMiddleware).
    Raises NotFoundException if no tenant context is resolved or if the tenant is inactive.
    """
    tenant_id_str = tenant_context.get()
    if not tenant_id_str:
        raise NotFoundException(
            message="Tenant context was not provided. Please supply X-Tenant-ID header or tenant_id query param.",
            code="TENANT_CONTEXT_MISSING"
        )
    
    # Check if tenant_id_str is a UUID or a subdomain string
    try:
        tenant_uuid = uuid.UUID(tenant_id_str)
        # Fetch by UUID
        tenant = await tenant_service.get_tenant(db, tenant_uuid)
    except ValueError:
        # If not a UUID, assume it's a subdomain and lookup
        tenant = await tenant_service.get_by_subdomain(db, redis, tenant_id_str)

    if not tenant.is_active:
        raise NotFoundException("The requested tenant account is currently deactivated.")
        
    return tenant


async def get_current_user(
    token: HTTPAuthorizationCredentials | None = Depends(reusable_oauth2),
) -> TokenPayload:
    """
    Dependency to authenticate request and extract JWT token payload.
    Validates token signature and expiration.
    """
    if not token:
        raise AuthenticationException("Authentication credentials were not provided.")
        
    try:
        payload = jwt.decode(
            token.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValueError) as err:
        raise AuthenticationException(
            message="Could not validate credentials: Token is invalid or expired.",
            code="INVALID_CREDENTIALS"
        )
        
    return token_data
