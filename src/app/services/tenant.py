import json
import uuid
from typing import Sequence
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.core.exceptions import BadRequestException, NotFoundException
from src.app.core.logging import logger
from src.app.models.tenant import Tenant
from src.app.repositories.tenant import TenantRepository, tenant_repository
from src.app.schemas.tenant import TenantCreate, TenantUpdate
from src.app.services.base import BaseService

CACHE_TTL = 3600  # Cache for 1 hour


class TenantService(BaseService[TenantRepository]):
    """
    Service layer coordinating business logic around Coaching Institutes (Tenants).
    Implements write-through/invalidation caching on Redis.
    """
    def __init__(self):
        super().__init__(tenant_repository)

    async def get_tenant(self, db: AsyncSession, id: uuid.UUID) -> Tenant:
        """Retrieves a tenant by UUID. Raises NotFoundException if not found."""
        tenant = await self.repository.get(db, id)
        if not tenant:
            raise NotFoundException(f"Tenant with ID '{id}' was not found.")
        return tenant

    async def get_by_subdomain(self, db: AsyncSession, redis: Redis, subdomain: str) -> Tenant:
        """
        Retrieves a tenant by subdomain, leveraging Redis caching.
        If cache hit, constructs a transient Tenant model.
        If cache miss, queries database, updates Redis, and returns the entity.
        """
        cache_key = f"tenant:subdomain:{subdomain}"
        
        # 1. Attempt cache lookup
        try:
            cached_data = await redis.get(cache_key)
            if cached_data:
                logger.debug("Redis cache hit for tenant subdomain", subdomain=subdomain)
                data = json.loads(cached_data)
                # Reconstruct a transient model instance for consistency
                # (without binding to active db session)
                return Tenant(
                    id=uuid.UUID(data["id"]),
                    name=data["name"],
                    subdomain=data["subdomain"],
                    settings=data["settings"],
                    is_active=data["is_active"]
                )
        except Exception as err:
            # Resilient to cache issues (fail-open to database)
            logger.error("Redis lookup failed in tenant service", error=str(err))

        # 2. Cache miss: Query Database
        tenant = await self.repository.get_by_subdomain(db, subdomain)
        if not tenant:
            raise NotFoundException(f"Tenant with subdomain '{subdomain}' does not exist.")

        # 3. Cache the retrieved data
        try:
            tenant_payload = {
                "id": str(tenant.id),
                "name": tenant.name,
                "subdomain": tenant.subdomain,
                "settings": tenant.settings,
                "is_active": tenant.is_active,
            }
            await redis.setex(cache_key, CACHE_TTL, json.dumps(tenant_payload))
            logger.debug("Redis cache populated for tenant subdomain", subdomain=subdomain)
        except Exception as err:
            logger.error("Redis write failed in tenant service", error=str(err))

        return tenant

    async def create_tenant(self, db: AsyncSession, obj_in: TenantCreate) -> Tenant:
        """Registers a new Coaching Institute after validating subdomain uniqueness."""
        existing = await self.repository.get_by_subdomain(db, obj_in.subdomain)
        if existing:
            raise BadRequestException(
                message=f"Subdomain '{obj_in.subdomain}' is already taken.",
                code="SUBDOMAIN_TAKEN"
            )
        return await self.repository.create(db, obj_in=obj_in)

    async def update_tenant(
        self, db: AsyncSession, redis: Redis, db_obj: Tenant, obj_in: TenantUpdate
    ) -> Tenant:
        """Updates tenant details and invalidates corresponding cache keys in Redis."""
        # Check if subdomain is being updated and if it's already taken
        if obj_in.subdomain and obj_in.subdomain != db_obj.subdomain:
            existing = await self.repository.get_by_subdomain(db, obj_in.subdomain)
            if existing:
                raise BadRequestException(
                    message=f"Subdomain '{obj_in.subdomain}' is already taken.",
                    code="SUBDOMAIN_TAKEN"
                )
        
        old_subdomain = db_obj.subdomain
        updated_tenant = await self.repository.update(db, db_obj=db_obj, obj_in=obj_in)
        
        # Invalidate old and new subdomain cache keys
        try:
            await redis.delete(f"tenant:subdomain:{old_subdomain}")
            if updated_tenant.subdomain != old_subdomain:
                await redis.delete(f"tenant:subdomain:{updated_tenant.subdomain}")
            logger.info("Invalidated Redis cache for updated tenant", subdomain=updated_tenant.subdomain)
        except Exception as err:
            logger.error("Failed to invalidate Redis cache after update", error=str(err))
            
        return updated_tenant


# Global service instance
tenant_service = TenantService()
