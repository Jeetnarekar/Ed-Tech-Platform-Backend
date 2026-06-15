from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.models.tenant import Tenant
from src.app.repositories.base import BaseRepository
from src.app.schemas.tenant import TenantCreate, TenantUpdate


class TenantRepository(BaseRepository[Tenant, TenantCreate, TenantUpdate]):
    """
    Repository class specifically for interacting with the Tenant entity.
    """
    def __init__(self):
        super().__init__(Tenant)

    async def get_by_subdomain(self, db: AsyncSession, subdomain: str) -> Tenant | None:
        """Retrieves a tenant by its unique subdomain."""
        statement = select(self.model).where(
            self.model.subdomain == subdomain,
            self.model.is_active == True
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()


# Global instance for reuse
tenant_repository = TenantRepository()
