from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.app.models.base import BaseModel


class Tenant(BaseModel):
    """
    Tenant entity representing a Coaching Institute.
    Each tenant has its own configuration settings, branding, and isolated data.
    """
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    subdomain: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    
    # Store settings dynamically (theme colors, branding, custom flags, limits, modules)
    settings: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, subdomain={self.subdomain})>"
