from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.app.core.logging import logger


class AppException(Exception):
    """Base application exception for business logic errors."""
    
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict | list | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundException(AppException):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str, code: str = "RESOURCE_NOT_FOUND", details: dict | list | None = None):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


class BadRequestException(AppException):
    """Raised when incoming data fails validation or client sends a bad request."""
    def __init__(self, message: str, code: str = "BAD_REQUEST", details: dict | list | None = None):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class AuthenticationException(AppException):
    """Raised when authentication credentials fail validation."""
    def __init__(self, message: str, code: str = "UNAUTHENTICATED", details: dict | list | None = None):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class ForbiddenException(AppException):
    """Raised when authorization fails (insufficient permissions)."""
    def __init__(self, message: str, code: str = "FORBIDDEN", details: dict | list | None = None):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers global exception handlers on the FastAPI instance."""
    
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "Application Exception caught",
            path=request.url.path,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        # Simplify validation error messages for the client
        details = [
            {"field": ".".join(map(str, err["loc"])), "message": err["msg"], "type": err["type"]}
            for err in errors
        ]
        
        logger.warning(
            "Request validation failed",
            path=request.url.path,
            errors_count=len(errors),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Input validation failed.",
                    "details": details,
                }
            }
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled server exception",
            path=request.url.path,
            error=str(exc),
            exc_info=True
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred.",
                    "details": None,
                }
            }
        )
