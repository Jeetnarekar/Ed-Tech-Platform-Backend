from pydantic import Field
from src.app.schemas.base import AuditSchema, SchemaBase


class TenantBase(SchemaBase):
    name: str = Field(..., max_length=255, description="Coaching Institute Name")
    subdomain: str = Field(..., max_length=100, pattern=r"^[a-z0-9\-]+$", description="Institute URL Subdomain")
    settings: dict = Field(default_factory=dict, description="Custom branding settings (branding, logos, features)")


class TenantCreate(TenantBase):
    pass


class TenantUpdate(SchemaBase):
    name: str | None = Field(None, max_length=255)
    subdomain: str | None = Field(None, max_length=100, pattern=r"^[a-z0-9\-]+$")
    settings: dict | None = None


class TenantOut(AuditSchema, TenantBase):
    pass
