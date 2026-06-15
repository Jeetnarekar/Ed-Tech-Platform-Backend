import uuid
from datetime import datetime
from typing import Sequence
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.models.email import EmailLog, EmailEvent
from src.app.models.tenant import Tenant
from src.app.repositories.base import BaseRepository
from src.app.schemas.email import EmailLogCreate, EmailLogUpdate, EmailEventCreate


class EmailLogRepository(BaseRepository[EmailLog, EmailLogCreate, EmailLogUpdate]):
    """
    Repository class handling queries and database CRUD for EmailLogs.
    Includes advanced analytical aggregation methods.
    """
    def __init__(self):
        super().__init__(EmailLog)

    async def get_by_message_id(self, db: AsyncSession, message_id: str) -> EmailLog | None:
        """Retrieves an EmailLog by its unique SES MessageID."""
        statement = select(self.model).options(selectinload(self.model.events)).where(
            self.model.message_id == message_id,
            self.model.is_active == True
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_tenant_history(
        self, db: AsyncSession, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[EmailLog]:
        """Retrieves paginated email logs for a specific tenant."""
        statement = (
            select(self.model)
            .options(selectinload(self.model.events))
            .where(
                self.model.tenant_id == tenant_id,
                self.model.is_active == True
            )
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        return result.scalars().all()

    async def get_analytics_summary(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """
        Aggregates sending totals and status breakdowns (Sent, Delivered, Opened, Clicked, Bounced, Complained)
        filtered by optional tenant_id and date boundaries.
        """
        conditions = [self.model.is_active == True]
        if tenant_id is not None:
            conditions.append(self.model.tenant_id == tenant_id)
        if start_date is not None:
            conditions.append(self.model.created_at >= start_date)
        if end_date is not None:
            conditions.append(self.model.created_at <= end_date)

        # Build aggregation query
        # Status mappings:
        # - Delivered includes open & click (as you cannot open/click without delivery)
        # - Opened includes click (as clicking links implies the email was opened)
        statement = select(
            func.count(self.model.id).label("total_sent"),
            func.count(
                case((self.model.status.in_(["delivered", "open", "click"]), 1))
            ).label("total_delivered"),
            func.count(
                case((self.model.status.in_(["open", "click"]), 1))
            ).label("total_opened"),
            func.count(
                case((self.model.status == "click", 1))
            ).label("total_clicked"),
            func.count(
                case((self.model.status == "bounce", 1))
            ).label("total_bounced"),
            func.count(
                case((self.model.status == "complaint", 1))
            ).label("total_complained"),
        ).where(*conditions)

        result = await db.execute(statement)
        row = result.fetchone()

        if not row:
            return {
                "total_sent": 0,
                "total_delivered": 0,
                "total_opened": 0,
                "total_clicked": 0,
                "total_bounced": 0,
                "total_complained": 0,
            }

        return {
            "total_sent": row[0] or 0,
            "total_delivered": row[1] or 0,
            "total_opened": row[2] or 0,
            "total_clicked": row[3] or 0,
            "total_bounced": row[4] or 0,
            "total_complained": row[5] or 0,
        }

    async def get_tenant_usage(
        self,
        db: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """
        Aggregates email volumes sent by each tenant for global usage reporting.
        """
        conditions = [self.model.is_active == True]
        if start_date is not None:
            conditions.append(self.model.created_at >= start_date)
        if end_date is not None:
            conditions.append(self.model.created_at <= end_date)

        statement = (
            select(
                self.model.tenant_id,
                Tenant.name.label("tenant_name"),
                func.count(self.model.id).label("email_count")
            )
            .outerjoin(Tenant, self.model.tenant_id == Tenant.id)
            .where(*conditions)
            .group_by(self.model.tenant_id, Tenant.name)
            .order_by(func.count(self.model.id).desc())
        )

        result = await db.execute(statement)
        rows = result.fetchall()

        return [
            {
                "tenant_id": row[0],
                "tenant_name": row[1] or "Global / System",
                "email_count": row[2] or 0
            }
            for row in rows
        ]


class EmailEventRepository(BaseRepository[EmailEvent, EmailEventCreate, EmailLogUpdate]):
    """
    Repository class handling queries and database CRUD for EmailEvents.
    """
    def __init__(self):
        super().__init__(EmailEvent)


email_log_repository = EmailLogRepository()
email_event_repository = EmailEventRepository()
