import json
import time
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.core.config import settings
from src.app.models.email import EmailLog, EmailEvent
from src.app.models.tenant import Tenant


def create_test_token(tenant_id: uuid.UUID | None = None) -> str:
    """Generates a mock JWT authorization token for testing route access."""
    import jwt
    payload = {
        "sub": str(uuid.uuid4()),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "exp": int(time.time()) + 3600
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@pytest.mark.asyncio
async def test_email_tracking_flow(client: AsyncClient, db_session: AsyncSession):
    """
    End-to-End integration test covering manual email sending,
    SNS webhook event ingestion, DB state updates, and analytical calculations.
    """
    # 1. Register a test Coaching Institute (Tenant)
    tenant_payload = {
        "name": "Beta Coaching Institute",
        "subdomain": "beta-coaching",
        "settings": {"allow_registration": True}
    }
    tenant_res = await client.post("/api/v1/tenants/", json=tenant_payload)
    assert tenant_res.status_code == 201
    tenant_data = tenant_res.json()
    tenant_id = uuid.UUID(tenant_data["id"])

    # Setup auth header & tenant scoping headers
    token = create_test_token(tenant_id=tenant_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": str(tenant_id)
    }

    # 2. Dispatch a manual test email (exercises Mock mode in test env)
    email_payload = {
        "recipient": "student@gmail.com",
        "subject": "Welcome to Beta Academy",
        "body": "Hi Student, welcome to your portal!"
    }
    send_res = await client.post("/api/v1/emails/send", json=email_payload, headers=headers)
    assert send_res.status_code == 201
    send_data = send_res.json()
    assert send_data["recipient"] == email_payload["recipient"]
    assert send_data["status"] == "sent"
    assert "message_id" in send_data
    message_id = send_data["message_id"]

    # Verify email record committed in DB
    query = select(EmailLog).where(EmailLog.message_id == message_id)
    db_result = await db_session.execute(query)
    email_log = db_result.scalar_one_or_none()
    assert email_log is not None
    assert email_log.tenant_id == tenant_id

    # 3. Simulate SES webhook 'Delivery' notification event from AWS SNS
    webhook_payload = {
        "Type": "Notification",
        "Message": json.dumps({
            "eventType": "Delivery",
            "mail": {
                "messageId": message_id,
                "timestamp": "2026-06-15T12:00:00.000Z",
                "destination": ["student@gmail.com"]
            },
            "delivery": {
                "timestamp": "2026-06-15T12:00:00.000Z",
                "recipients": ["student@gmail.com"]
            }
        })
    }
    
    # Send webhook with valid secret
    webhook_res = await client.post(
        f"/api/v1/emails/webhook/ses?secret={settings.SES_WEBHOOK_SECRET}",
        json=webhook_payload
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["status"] == "processed"

    # Refresh DB session and verify status updated
    await db_session.refresh(email_log)
    assert email_log.status == "delivered"

    # 4. Simulate SES webhook 'Open' notification event
    open_payload = {
        "Type": "Notification",
        "Message": json.dumps({
            "eventType": "Open",
            "mail": {
                "messageId": message_id,
                "timestamp": "2026-06-15T12:05:00.000Z",
                "destination": ["student@gmail.com"]
            },
            "open": {
                "timestamp": "2026-06-15T12:05:00.000Z"
            }
        })
    }
    open_res = await client.post(
        f"/api/v1/emails/webhook/ses?secret={settings.SES_WEBHOOK_SECRET}",
        json=open_payload
    )
    assert open_res.status_code == 200
    await db_session.refresh(email_log)
    assert email_log.status == "open"

    # 5. Query Tenant-Specific Analytics Summary
    analytics_res = await client.get("/api/v1/emails/tenant/analytics", headers=headers)
    assert analytics_res.status_code == 200
    analytics_data = analytics_res.json()
    
    assert analytics_data["total_sent"] == 1
    assert analytics_data["total_delivered"] == 1
    assert analytics_data["total_opened"] == 1
    assert analytics_data["total_bounced"] == 0
    assert analytics_data["delivery_rate"] == 100.0
    assert analytics_data["open_rate"] == 100.0
    assert analytics_data["bounce_rate"] == 0.0

    # 6. Query Global Admin Analytics (without tenant context)
    super_token = create_test_token(tenant_id=None)
    super_headers = {
        "Authorization": f"Bearer {super_token}"
    }
    global_res = await client.get("/api/v1/emails/analytics", headers=super_headers)
    assert global_res.status_code == 200
    global_data = global_res.json()
    
    assert global_data["summary"]["total_sent"] == 1
    assert global_data["summary"]["total_opened"] == 1
    assert len(global_data["tenant_usage"]) > 0
    assert global_data["tenant_usage"][0]["tenant_id"] == str(tenant_id)
    assert global_data["tenant_usage"][0]["email_count"] == 1

    # 7. Check email history endpoints
    history_res = await client.get("/api/v1/emails/history", headers=headers)
    assert history_res.status_code == 200
    history_data = history_res.json()
    assert len(history_data) == 1
    assert history_data[0]["message_id"] == message_id
    assert history_data[0]["status"] == "open"


@pytest.mark.asyncio
async def test_webhook_secret_validation(client: AsyncClient):
    """Verifies that the SES Webhook rejects payloads with incorrect secret tokens."""
    payload = {"Type": "Notification"}
    res = await client.post(
        "/api/v1/emails/webhook/ses?secret=incorrect-secret",
        json=payload
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "INVALID_WEBHOOK_SECRET"


@pytest.mark.asyncio
async def test_global_analytics_forbidden_for_tenant_users(client: AsyncClient):
    """Verifies that tenant admins are blocked from querying global dashboard metrics."""
    tenant_id = uuid.uuid4()
    token = create_test_token(tenant_id=tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    
    res = await client.get("/api/v1/emails/analytics", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"
