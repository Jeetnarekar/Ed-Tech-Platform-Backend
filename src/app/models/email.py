import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.app.models.base import BaseModel


class EmailLog(BaseModel):
    """
    Tracks all emails sent from the application, tied to optional tenant context
    and dynamic tracking status.
    """
    __tablename__ = "email_logs"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    recipient: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    
    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    message_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="sent",
        server_default="sent",
        index=True,
    )
    
    # Relationship to events
    events: Mapped[list["EmailEvent"]] = relationship(
        "EmailEvent",
        back_populates="email_log",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<EmailLog(id={self.id}, recipient={self.recipient}, status={self.status}, message_id={self.message_id})>"


class EmailEvent(BaseModel):
    """
    Stores individual events received via webhooks (e.g. Delivery, Bounce, Open, Click).
    Used for analytical aggregations and audit trailing.
    """
    __tablename__ = "email_events"

    email_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("email_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    raw_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    
    # Relationship back to the email log
    email_log: Mapped[EmailLog] = relationship(
        "EmailLog",
        back_populates="events",
    )

    def __repr__(self) -> str:
        return f"<EmailEvent(id={self.id}, email_log_id={self.email_log_id}, event_type={self.event_type}, timestamp={self.timestamp})>"
