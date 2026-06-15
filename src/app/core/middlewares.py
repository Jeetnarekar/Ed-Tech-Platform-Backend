import time
from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from src.app.core.logging import logger

# ContextVar to store the current tenant context for the lifecycle of a request
tenant_context: ContextVar[str | None] = ContextVar("tenant_context", default=None)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to resolve tenant context from HTTP request headers.
    In production SaaS, this can be resolved from:
    1. A header (e.g. X-Tenant-ID)
    2. Subdomain (e.g. tenant1.coachingapp.com)
    3. Query parameter (e.g. ?tenant_id=XYZ)
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # Resolve Tenant ID from header or query param as a fallback
        tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
        
        # Token to reset ContextVar back to previous state
        token = tenant_context.set(tenant_id)
        
        try:
            response = await call_next(request)
            # Make sure tenant id is appended to response headers for validation
            if tenant_id:
                response.headers["X-Tenant-ID"] = tenant_id
            return response
        finally:
            # Reset context variable to prevent cross-request leakage
            tenant_context.reset(token)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log information about every incoming HTTP request and response,
    including total time taken to process the request.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        
        # Log request receipt
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
            tenant_id=tenant_context.get()
        )
        
        try:
            response = await call_next(request)
            process_time = time.perf_counter() - start_time
            
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=f"{process_time:.4f}s",
                tenant_id=tenant_context.get()
            )
            return response
        except Exception as exc:
            process_time = time.perf_counter() - start_time
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                duration=f"{process_time:.4f}s",
                error=str(exc),
                tenant_id=tenant_context.get()
            )
            raise
