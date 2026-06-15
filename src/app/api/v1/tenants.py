import uuid
from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.api import deps
from src.app.schemas.tenant import TenantCreate, TenantOut, TenantUpdate
from src.app.services.tenant import tenant_service

router = APIRouter()


@router.post(
    "/",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new Coaching Institute Tenant",
)
async def register_tenant(
    payload: TenantCreate,
    db: AsyncSession = Depends(deps.get_async_db),
):
    """
    Registers a new Coaching Institute Tenant in the system.
    This creates their subdomain mapping and dynamic configuration settings block.
    """
    return await tenant_service.create_tenant(db, obj_in=payload)


@router.get(
    "/{tenant_id}",
    response_model=TenantOut,
    summary="Get tenant details by UUID",
)
async def get_tenant_by_id(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_async_db),
):
    """
    Retrieves info for a coaching institute by its system UUID.
    """
    return await tenant_service.get_tenant(db, tenant_id)


@router.get(
    "/subdomain/{subdomain}",
    response_model=TenantOut,
    summary="Get tenant details by Subdomain",
)
async def get_tenant_by_subdomain(
    subdomain: str,
    db: AsyncSession = Depends(deps.get_async_db),
    redis: Redis = Depends(deps.get_redis),
):
    """
    Retrieves info for a coaching institute by its subdomain.
    Utilizes Redis cache lookup for quick responses.
    """
    return await tenant_service.get_by_subdomain(db, redis, subdomain=subdomain)


@router.put(
    "/{tenant_id}",
    response_model=TenantOut,
    summary="Update tenant details",
)
async def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    db: AsyncSession = Depends(deps.get_async_db),
    redis: Redis = Depends(deps.get_redis),
):
    """
    Updates the registration details or settings configuration for a Coaching Institute.
    Invalidates associated Redis cache entries.
    """
    tenant = await tenant_service.get_tenant(db, tenant_id)
    return await tenant_service.update_tenant(db, redis, db_obj=tenant, obj_in=payload)
