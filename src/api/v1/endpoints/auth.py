from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from src.api.v1.deps import get_auth_service, get_current_user
from src.models.user import User
from src.schemas.user import (
    AuthResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
)
from src.services.auth import AuthService
from src.utils.rate_limiter import limiter

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация",
    description=(
        "Создаёт новый аккаунт. Сразу возвращает токены и данные пользователя — "
        "дополнительный вызов /login не нужен. "
        "Повторный вызов с тем же email вернёт **409 Conflict**."
    ),
)
@limiter.limit("3/minute")
async def register(
    request: Request,
    user_in: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    return await auth_service.register_new_user(user_in)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Вход",
    description=(
        "Аутентификация по email и паролю. "
        "Возвращает токены и данные пользователя. "
        "Повторный вызов для уже авторизованного пользователя выдаёт новую пару токенов — "
        "старые остаются валидными до истечения срока (stateless JWT)."
    ),
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    return await auth_service.authenticate(form_data.username, form_data.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Обновление токенов",
    description=(
        "Принимает действующий **refresh_token** и выдаёт новую пару access + refresh токенов. "
        "Передавайте refresh_token в теле запроса, не в заголовке Authorization."
    ),
)
async def refresh_tokens(
    body: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await auth_service.refresh_tokens(body.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Выход из системы",
    description=(
        "Выход из системы с инвалидацией токенов через Redis blacklist. Требует передачи access и refresh токенов в заголовках."
    ),
)
async def logout(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    authorization: str | None = Header(
        default=None,
        description="Access token в формате 'Bearer <token>'",
    ),
    x_refresh_token: str | None = Header(
        default=None,
        description="Refresh token",
    ),
) -> dict[str, str]:
    """
    Выход из системы с инвалидацией токенов.

    Добавляет access и refresh токены в blacklist для предотвращения
    их повторного использования до момента истечения срока действия.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    access_token = authorization.replace("Bearer ", "")

    if not x_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token in X-Refresh-Token header",
        )

    await auth_service.logout(access_token, x_refresh_token)
    return {"message": "Successfully logged out"}


@router.post(
    "/password-reset",
    status_code=status.HTTP_200_OK,
    summary="Запрос сброса пароля",
    description=(
        "Запрашивает сброс пароля. Отправляет email с инструкциями. "
        "Если email существует — возвращает успех (не раскрывает существование пользователя)."
    ),
)
@limiter.limit("3/hour")
async def request_password_reset(
    request: Request,
    reset_request: PasswordResetRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """
    Запрос на сброс пароля.

    Отправляет email со ссылкой для сброса пароля.
    Для безопасности не раскрывает, существует ли пользователь с таким email.
    """
    return await auth_service.request_password_reset(reset_request.email)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_200_OK,
    summary="Подтверждение сброса пароля",
    description="Устанавливает новый пароль используя токен из email.",
)
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """
    Подтверждение сброса пароля.

    Устанавливает новый пароль если токен действителен и не истёк.
    """
    return await auth_service.confirm_password_reset(
        token=reset_confirm.token,
        new_password=reset_confirm.new_password,
    )
