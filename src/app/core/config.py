import os
from typing import Literal
from pydantic import Field, PostgresDsn, RedisDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Project Information
    PROJECT_NAME: str = "EdTech SaaS Platform"
    ENV: Literal["development", "staging", "production", "testing"] = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # PostgreSQL Configuration
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_DB: str | None = None
    DATABASE_POOL_SIZE: int = 2
    DATABASE_MAX_OVERFLOW: int = 0

    # Redis Configuration
    REDIS_HOST: str | None = None
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    JSON_LOGS: bool = False

    # AWS / SES Configuration
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-1"
    SES_SENDER_EMAIL: str = "noreply@example.com"
    SES_WEBHOOK_SECRET: str = "development-secret-token"

    # Assembled Connection URIs
    DATABASE_URL: str = ""
    REDIS_URL: str = ""

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str, info: ValidationInfo) -> str:
        if v:
            # SQLAlchemy asyncpg requires postgresql+asyncpg:// protocol scheme
            if v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            return v
        data = info.data
        user = data.get("POSTGRES_USER")
        password = data.get("POSTGRES_PASSWORD")
        host = data.get("POSTGRES_HOST")
        port = data.get("POSTGRES_PORT")
        db = data.get("POSTGRES_DB")
        if not all([user, password, host, db]):
            raise ValueError("Either DATABASE_URL or all POSTGRES_* configuration variables must be set.")
        # We use asyncpg for FastAPI runtime
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def assemble_redis_connection(cls, v: str, info: ValidationInfo) -> str:
        if v:
            return v
        data = info.data
        host = data.get("REDIS_HOST") or "localhost"
        port = data.get("REDIS_PORT") or 6379
        db = data.get("REDIS_DB") or 0
        password = data.get("REDIS_PASSWORD")
        
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{host}:{port}/{db}"


# Global instance of Settings
settings = Settings()
