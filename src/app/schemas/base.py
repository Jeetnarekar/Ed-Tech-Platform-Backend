import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SchemaBase(BaseModel):
    """Base schema config for all model-backed Pydantic schemas."""
    model_config = ConfigDict(from_attributes=True)


class AuditSchema(SchemaBase):
    """Common read fields for resources that inherit from BaseModel."""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    is_active: bool
