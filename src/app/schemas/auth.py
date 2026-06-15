import uuid
from src.app.schemas.base import SchemaBase


class Token(SchemaBase):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(SchemaBase):
    sub: uuid.UUID | str | None = None
    tenant_id: uuid.UUID | str | None = None
    exp: int | None = None


class LoginRequest(SchemaBase):
    username: str
    password: str
    tenant_id: uuid.UUID | None = None
