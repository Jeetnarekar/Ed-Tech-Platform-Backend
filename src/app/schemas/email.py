import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class EmailSendRequest(BaseModel):
    """Schema for requesting a manual/test email dispatch."""
    recipient: EmailStr = Field(..., description="Recipient email address")
    subject: str = Field(..., max_length=255, description="Email subject line")
    body: str = Field(..., description="Email body content (text/HTML)")


class EmailEventResponse(BaseModel):
    """Schema for a single tracked email event."""
    id: uuid.UUID
    email_log_id: uuid.UUID
    event_type: str
    timestamp: datetime
    raw_data: dict
    created_at: datetime

    class Config:
        from_attributes = True


class EmailLogResponse(BaseModel):
    """Schema for returning email dispatch metadata and status."""
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    recipient: str
    subject: str
    message_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    events: list[EmailEventResponse] = []

    class Config:
        from_attributes = True


class EmailAnalyticsSummary(BaseModel):
    """Aggregate rates and counts for reporting email engagement metrics."""
    total_sent: int = Field(0, description="Total emails sent out")
    total_delivered: int = Field(0, description="Total emails successfully delivered")
    total_opened: int = Field(0, description="Total unique email opens detected")
    total_clicked: int = Field(0, description="Total unique email link clicks detected")
    total_bounced: int = Field(0, description="Total emails bounced")
    total_complained: int = Field(0, description="Total spam complaints received")
    
    delivery_rate: float = Field(0.0, description="Percentage of emails delivered: (delivered / sent) * 100")
    bounce_rate: float = Field(0.0, description="Percentage of emails bounced: (bounced / sent) * 100")
    complaint_rate: float = Field(0.0, description="Percentage of complaints: (complained / sent) * 100")
    open_rate: float = Field(0.0, description="Percentage of delivered emails opened: (opened / delivered) * 100")
    click_rate: float = Field(0.0, description="Percentage of delivered emails clicked: (clicked / delivered) * 100")


class TenantEmailUsage(BaseModel):
    """Usage stats grouped by individual tenants (coaching institutes)."""
    tenant_id: uuid.UUID | None
    tenant_name: str | None
    email_count: int


class GlobalEmailAnalytics(BaseModel):
    """Cross-tenant email analytics for global admin visibility."""
    summary: EmailAnalyticsSummary
    tenant_usage: list[TenantEmailUsage]


class EmailLogCreate(BaseModel):
    tenant_id: uuid.UUID | None = None
    recipient: str
    subject: str
    message_id: str
    status: str = "sent"


class EmailLogUpdate(BaseModel):
    status: str | None = None
    message_id: str | None = None


class EmailEventCreate(BaseModel):
    email_log_id: uuid.UUID
    event_type: str
    timestamp: datetime
    raw_data: dict

