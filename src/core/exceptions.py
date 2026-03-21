from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Базовое исключение для всего приложения."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.message = message
        self.status_code = status_code


class UserAlreadyExistsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Пользователь с таким email уже зарегистрирован",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidCredentialsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Неверный email или пароль", status_code=status.HTTP_401_UNAUTHORIZED
        )


class PermissionDeniedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            message="Недостаточно прав для выполнения операции",
            status_code=status.HTTP_403_FORBIDDEN,
        )


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.__class__.__name__},
        )
