from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.api import deps
from src.app.core.config import settings
from src.app.core.exceptions import ForbiddenException
from src.app.schemas.auth import TokenPayload
from src.app.schemas.email import (
    EmailAnalyticsSummary,
    EmailLogResponse,
    EmailSendRequest,
    GlobalEmailAnalytics,
)
from src.app.services.email import email_service

router = APIRouter()


@router.post("/webhook/ses", status_code=status.HTTP_200_OK, include_in_schema=True)
async def ses_webhook(
    request: Request,
    secret: str = Query(..., description="Webhook verification secret token"),
    db: AsyncSession = Depends(deps.get_async_db),
) -> Any:
    """
    Public webhook endpoint for AWS SES Event Publishing (via SNS/EventBridge).
    Validates query secret and processes delivery, open, click, bounce, or complaint events.
    """
    if secret != settings.SES_WEBHOOK_SECRET:
        raise ForbiddenException(
            message="Invalid webhook secret token provided.",
            code="INVALID_WEBHOOK_SECRET"
        )
    
    payload = await request.json()
    result = await email_service.process_ses_event(db, payload)
    return result


@router.post("/send", response_model=EmailLogResponse, status_code=status.HTTP_201_CREATED)
async def send_manual_email(
    email_in: EmailSendRequest,
    db: AsyncSession = Depends(deps.get_async_db),
    tenant: Any = Depends(deps.get_current_tenant),
) -> Any:
    """
    Dispatches a manual email scoped to the active tenant/institute context.
    """
    # Send email through service (which selects SES or Mock based on config)
    created_log = await email_service.send_email(db, tenant_id=tenant.id, email_in=email_in)
    return created_log


@router.get("/tenant/analytics", response_model=EmailAnalyticsSummary)
async def get_tenant_email_analytics(
    start_date: datetime | None = Query(None, description="Start boundary (ISO format)"),
    end_date: datetime | None = Query(None, description="End boundary (ISO format)"),
    db: AsyncSession = Depends(deps.get_async_db),
    tenant: Any = Depends(deps.get_current_tenant),
) -> Any:
    """
    Retrieves email engagement analytics summary (sent, delivery rates, opens, bounces)
    for the active tenant/institute.
    """
    analytics = await email_service.get_tenant_analytics(
        db, tenant_id=tenant.id, start_date=start_date, end_date=end_date
    )
    return analytics


@router.get("/analytics", response_model=GlobalEmailAnalytics)
async def get_global_email_analytics(
    start_date: datetime | None = Query(None, description="Start boundary (ISO format)"),
    end_date: datetime | None = Query(None, description="End boundary (ISO format)"),
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: TokenPayload = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieves system-wide cross-tenant email usage and summary metrics.
    Only accessible to global system administrators (without a specific tenant_id bound to their JWT).
    """
    if current_user.tenant_id is not None:
        raise ForbiddenException(
            message="Access denied: Global analytics require system administrator privileges.",
            code="SUPER_ADMIN_REQUIRED"
        )

    global_stats = await email_service.get_global_analytics(
        db, start_date=start_date, end_date=end_date
    )
    return global_stats


@router.get("/history", response_model=list[EmailLogResponse])
async def get_email_sending_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(deps.get_async_db),
    tenant: Any = Depends(deps.get_current_tenant),
) -> Any:
    """
    Retrieves history logs of all emails sent by the active tenant/institute,
    ordered by creation date (newest first).
    """
    history = await email_service.repository.get_tenant_history(
        db, tenant_id=tenant.id, skip=skip, limit=limit
    )
    return history


@router.get("/test-token", status_code=200, include_in_schema=True)
async def generate_test_token(
    tenant_id: str | None = Query(None, description="Optional tenant UUID to bind to the token payload")
) -> Any:
    """
    Generates a valid signed JWT authorization token for testing and local dashboard client requests.
    """
    import jwt
    import time
    payload = {
        "sub": "test-user-id",
        "tenant_id": tenant_id if tenant_id else None,
        "exp": int(time.time()) + 3600 * 24  # 24 hours validity
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return {"token": token}

