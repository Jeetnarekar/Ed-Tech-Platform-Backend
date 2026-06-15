from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.app.api.v1.router import api_router
from src.app.core.config import settings
from src.app.core.exceptions import register_exception_handlers
from src.app.core.logging import logger, setup_logging
from src.app.core.middlewares import LoggingMiddleware, TenantMiddleware
from src.app.core.redis import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifecycle context manager.
    Coordinates app bootstrapping (logging, caching pools) and teardown.
    """
    # 1. Startup phase
    setup_logging()
    logger.info("Starting up FastAPI application...", env=settings.ENV, debug=settings.DEBUG)
    
    # Initialize redis connection pool
    init_redis()
    
    yield
    
    # 2. Shutdown phase
    logger.info("Shutting down FastAPI application...")
    await close_redis()


# Instantiate FastAPI Application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-ready multi-tenant SaaS backend foundation.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Register Middlewares (Note: Starlette executes middlewares in reverse order of registration)
# Register CORS middleware to permit frontend clients to query the api
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in staging/production configs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middlewares
app.add_middleware(LoggingMiddleware)
app.add_middleware(TenantMiddleware)

# Register Custom Domain/HTTP Exception Handlers
register_exception_handlers(app)

# Include Router endpoints
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", include_in_schema=False)
async def root():
    """Root redirect / index greeting."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "docs_url": "/docs",
        "status": "active"
    }
