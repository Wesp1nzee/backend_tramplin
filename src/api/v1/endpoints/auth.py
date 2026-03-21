from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from src.api.v1.deps import get_auth_service
from src.schemas.user import AuthResponse, RefreshTokenRequest, TokenResponse, UserCreate
from src.services.auth import AuthService

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
async def register(
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
async def login(
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
