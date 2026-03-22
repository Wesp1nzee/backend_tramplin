import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


class AppError(Exception):
    """
    Базовый класс для всех доменных исключений.
    Наследники объявляют status_code, detail и error_code на уровне класса —
    это позволяет raise SomeError() без аргументов и получить
    осмысленный HTTP-ответ через глобальный обработчик.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Internal server error"
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


# ─── Authentication Errors (401, 403) ───
class AuthenticationError(AppError):
    """Базовый класс для ошибок аутентификации."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "AUTHENTICATION_FAILED"


class InvalidCredentialsError(AuthenticationError):
    detail = "Invalid email or password"


class InvalidTokenError(AuthenticationError):
    detail = "Invalid or expired token"


class UserNotActiveError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "User account is deactivated"
    error_code = "USER_NOT_ACTIVE"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "Not enough permissions"
    error_code = "PERMISSION_DENIED"


# ─── User Errors (400, 404, 409) ───
class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"
    error_code = "NOT_FOUND"


class UserAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "User with this email already exists"
    error_code = "USER_ALREADY_EXISTS"


# ─── Repository/Database Errors ───
class RepositoryError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "REPOSITORY_ERROR"
    detail = "Database operation failed"


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
        """Обработчик доменных исключений."""
        if exc.status_code >= 500:
            logger.error(f"Server error: {exc.error_code}", detail=exc.detail)
        else:
            logger.warning(f"Client error: {exc.error_code}", detail=exc.detail)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.detail,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Обработчик валидации Pydantic."""
        # Convert errors to JSON-serializable format (ValueError -> str)
        errors = []
        for error in exc.errors():
            err_copy = error.copy()
            if "ctx" in err_copy and err_copy["ctx"]:
                ctx = {}
                for key, value in err_copy["ctx"].items():
                    if isinstance(value, Exception):
                        ctx[key] = str(value)
                    else:
                        ctx[key] = value
                err_copy["ctx"] = ctx
            errors.append(err_copy)

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": errors,
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Fallback для необработанных исключений."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                }
            },
        )
