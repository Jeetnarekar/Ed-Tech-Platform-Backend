import json
import uuid
from datetime import datetime, timezone
import boto3
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from src.app.core.config import settings
from src.app.core.exceptions import AppException, BadRequestException, NotFoundException
from src.app.core.logging import logger
from src.app.schemas.email import (
    EmailAnalyticsSummary,
    EmailEventCreate,
    EmailLogCreate,
    EmailLogUpdate,
    EmailSendRequest,
    GlobalEmailAnalytics,
    TenantEmailUsage,
)
from src.app.repositories.email import email_log_repository, email_event_repository
from src.app.services.base import BaseService

STATUS_PRECEDENCE = {
    "sent": 1,
    "delivered": 2,
    "open": 3,
    "click": 4,
    "bounce": 5,
    "complaint": 5,
    "reject": 5,
}

EVENT_TO_STATUS_MAP = {
    "send": "sent",
    "delivery": "delivered",
    "open": "open",
    "click": "click",
    "bounce": "bounce",
    "complaint": "complaint",
    "reject": "reject",
}


class EmailService(BaseService[type(email_log_repository)]):
    """
    Service layer coordinating email dispatches, webhook processing,
    and analytical aggregates for email health.
    """
    def __init__(self):
        super().__init__(email_log_repository)

    async def send_email(
        self, db: AsyncSession, *, tenant_id: uuid.UUID | None, email_in: EmailSendRequest
    ) -> EmailLogCreate:
        """
        Sends an email via Amazon SES (or local mock fallback) and logs the event.
        """
        # Determine if we have real AWS credentials configured
        aws_configured = all([
            settings.AWS_ACCESS_KEY_ID,
            settings.AWS_SECRET_ACCESS_KEY
        ]) or settings.ENV == "production"  # In prod, we may use IAM roles instead

        message_id = None
        
        if aws_configured:
            try:
                # Initialize boto3 client
                # (uses credentials if present, otherwise defaults to IAM role credentials in ECS/EKS)
                client_kwargs = {"region_name": settings.AWS_REGION}
                if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                    client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                    client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

                ses_client = boto3.client("ses", **client_kwargs)
                
                response = ses_client.send_email(
                    Source=settings.SES_SENDER_EMAIL,
                    Destination={
                        "ToAddresses": [email_in.recipient],
                    },
                    Message={
                        "Subject": {
                            "Data": email_in.subject,
                            "Charset": "UTF-8",
                        },
                        "Body": {
                            "Html": {
                                "Data": email_in.body,
                                "Charset": "UTF-8",
                            } if "<html" in email_in.body.lower() else {
                                "Data": email_in.body,
                                "Charset": "UTF-8",
                            }
                        },
                    },
                )
                message_id = response.get("MessageId")
                logger.info(
                    "Email sent successfully via Amazon SES",
                    recipient=email_in.recipient,
                    message_id=message_id,
                    tenant_id=tenant_id,
                )
            except Exception as err:
                logger.error(
                    "Failed to dispatch email via AWS SES",
                    recipient=email_in.recipient,
                    error=str(err),
                    tenant_id=tenant_id,
                )
                raise AppException(
                    message=f"Email delivery failed: {str(err)}",
                    code="EMAIL_DISPATCH_FAILED",
                )
        else:
            # Fallback to local mock mode
            message_id = f"mock-ses-msg-{uuid.uuid4()}"
            logger.info(
                "[MOCK MODE] Email sent successfully",
                recipient=email_in.recipient,
                subject=email_in.subject,
                body=email_in.body[:100] + "..." if len(email_in.body) > 100 else email_in.body,
                message_id=message_id,
                tenant_id=tenant_id,
            )

        # Record to Database
        db_in = EmailLogCreate(
            tenant_id=tenant_id,
            recipient=email_in.recipient,
            subject=email_in.subject,
            message_id=message_id,
            status="sent",
        )
        created_log = await self.repository.create(db, obj_in=db_in)
        set_committed_value(created_log, "events", [])
        return created_log

    async def process_ses_event(self, db: AsyncSession, raw_payload: dict) -> dict:
        """
        Parses incoming SNS notifications or EventBridge events from AWS SES,
        tracks events in the DB, and updates target email log status.
        """
        # 1. Handle SNS Subscription Confirmation
        if raw_payload.get("Type") == "SubscriptionConfirmation":
            subscribe_url = raw_payload.get("SubscribeURL")
            if subscribe_url:
                logger.info("Received SNS Subscription Confirmation request. Triggering subscription...", url=subscribe_url)
                # Call AWS SNS to confirm the subscription endpoint asynchronously
                async with httpx.AsyncClient() as client:
                    response = await client.get(subscribe_url)
                    if response.status_code == 200:
                        logger.info("SNS Webhook Subscription confirmed successfully!")
                        return {"status": "subscription_confirmed"}
                    else:
                        logger.error("Failed to confirm SNS Webhook Subscription", status_code=response.status_code)
                        raise BadRequestException("Failed to confirm SNS Subscription.")
            raise BadRequestException("Missing SubscribeURL for subscription confirmation.")

        # 2. Extract Event Notification
        message_data = raw_payload
        if raw_payload.get("Type") == "Notification":
            try:
                # SNS Notification message wraps the SES event as a JSON string inside 'Message'
                message_data = json.loads(raw_payload.get("Message", "{}"))
            except json.JSONDecodeError:
                logger.error("Failed to parse raw SNS message content as JSON")
                raise BadRequestException("Notification message is not valid JSON.")

        # Event fields standard format (SES Event Publishing JSON Schema)
        event_type = message_data.get("eventType") or message_data.get("detail", {}).get("eventType")
        mail_data = message_data.get("mail") or message_data.get("detail", {}).get("mail")

        if not event_type or not mail_data:
            logger.warning("Webhook received invalid/non-SES event payload format")
            return {"status": "ignored", "reason": "non_ses_event"}

        message_id = mail_data.get("messageId")
        if not message_id:
            logger.warning("SES Event payload is missing messageId")
            raise BadRequestException("SES event payload requires messageId.")

        # 3. Locate target email record
        email_log = await self.repository.get_by_message_id(db, message_id)
        if not email_log:
            logger.warning("Received SES event for unknown messageId", message_id=message_id)
            return {"status": "ignored", "reason": "unknown_message_id"}

        # 4. Resolve timestamp and type
        event_type_lower = event_type.lower()
        
        # Resolve timestamp from SES payload if available, else current UTC
        timestamp_str = mail_data.get("timestamp")
        if timestamp_str:
            try:
                # Strip 'Z' or offset if python datetime parser needs it
                event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                event_time = datetime.now(timezone.utc)
        else:
            event_time = datetime.now(timezone.utc)

        # 5. Record the granular event
        event_in = EmailEventCreate(
            email_log_id=email_log.id,
            event_type=event_type_lower,
            timestamp=event_time,
            raw_data=message_data,
        )
        await email_event_repository.create(db, obj_in=event_in)

        # 6. Conditionally update status based on precedence rules
        target_status = EVENT_TO_STATUS_MAP.get(event_type_lower, event_type_lower)
        current_status = email_log.status
        current_prec = STATUS_PRECEDENCE.get(current_status, 0)
        new_prec = STATUS_PRECEDENCE.get(target_status, 0)

        if new_prec >= current_prec:
            update_in = EmailLogUpdate(status=target_status)
            await self.repository.update(db, db_obj=email_log, obj_in=update_in)
            logger.info(
                "Updated email log status",
                message_id=message_id,
                recipient=email_log.recipient,
                old_status=current_status,
                new_status=target_status,
            )

        return {"status": "processed", "message_id": message_id, "event": target_status}

    async def get_tenant_analytics(
        self, db: AsyncSession, tenant_id: uuid.UUID, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> EmailAnalyticsSummary:
        """
        Retrieves sending health statistics for a specific Coaching Institute (tenant).
        """
        summary_data = await self.repository.get_analytics_summary(
            db, tenant_id=tenant_id, start_date=start_date, end_date=end_date
        )
        return self._calculate_rates(summary_data)

    async def get_global_analytics(
        self, db: AsyncSession, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> GlobalEmailAnalytics:
        """
        Retrieves global metrics including totals and usage breakdowns per tenant.
        """
        global_summary = await self.repository.get_analytics_summary(
            db, tenant_id=None, start_date=start_date, end_date=end_date
        )
        summary = self._calculate_rates(global_summary)

        usage_rows = await self.repository.get_tenant_usage(
            db, start_date=start_date, end_date=end_date
        )
        
        tenant_usages = [
            TenantEmailUsage(
                tenant_id=row["tenant_id"],
                tenant_name=row["tenant_name"],
                email_count=row["email_count"]
            )
            for row in usage_rows
        ]

        return GlobalEmailAnalytics(
            summary=summary,
            tenant_usage=tenant_usages
        )

    def _calculate_rates(self, data: dict) -> EmailAnalyticsSummary:
        """Computes rates (open rate, bounce rate, etc.) from aggregates."""
        sent = data["total_sent"]
        delivered = data["total_delivered"]
        bounced = data["total_bounced"]
        complained = data["total_complained"]
        opened = data["total_opened"]
        clicked = data["total_clicked"]

        delivery_rate = round((delivered / sent) * 100, 2) if sent > 0 else 0.0
        bounce_rate = round((bounced / sent) * 100, 2) if sent > 0 else 0.0
        complaint_rate = round((complained / sent) * 100, 2) if sent > 0 else 0.0
        open_rate = round((opened / delivered) * 100, 2) if delivered > 0 else 0.0
        click_rate = round((clicked / delivered) * 100, 2) if delivered > 0 else 0.0

        return EmailAnalyticsSummary(
            total_sent=sent,
            total_delivered=delivered,
            total_opened=opened,
            total_clicked=clicked,
            total_bounced=bounced,
            total_complained=complained,
            delivery_rate=delivery_rate,
            bounce_rate=bounce_rate,
            complaint_rate=complaint_rate,
            open_rate=open_rate,
            click_rate=click_rate,
        )


email_service = EmailService()
