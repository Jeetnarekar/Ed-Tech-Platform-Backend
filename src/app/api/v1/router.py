from fastapi import APIRouter
from src.app.api.v1 import health, tenants, emails

api_router = APIRouter()

# Register core v1 routers
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
api_router.include_router(emails.router, prefix="/emails", tags=["Emails"])
