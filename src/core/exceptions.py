from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """
    Базовый класс для всех доменных исключений.
    Наследники объявляют status_code и detail на уровне класса —
    это позволяет raise SomeError() без аргументов и получить
    осмысленный HTTP-ответ через глобальный обработчик.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class UserAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "User with this email already exists"


class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Invalid email or password"


class InvalidTokenError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Invalid or expired token"


class UserNotActiveError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "User account is deactivated"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "Not enough permissions"


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
