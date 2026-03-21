import uuid

import structlog

from src.core.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    UserAlreadyExistsError,
    UserNotActiveError,
)
from src.core.security import create_tokens, decode_token, hash_password, verify_password
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.user import UserRepository
from src.schemas.user import AuthResponse, TokenResponse, UserCreate

logger = structlog.get_logger()


class AuthService:
    """
    Бизнес-логика аутентификации.
    """

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def register_new_user(self, user_in: UserCreate) -> AuthResponse:
        """
        Регистрирует нового пользователя и сразу выдаёт токены.

        Логика верификации:
        - EMPLOYER требует ручной верификации куратором (is_verified=False)
        - Остальные роли верифицируются автоматически
        TODO: заменить на email-верификацию для всех ролей
        """
        if await self.user_repo.email_exists(user_in.email):
            raise UserAlreadyExistsError()

        new_user = User(
            email=user_in.email,
            hashed_password=hash_password(user_in.password),
            role=user_in.role,
            is_verified=user_in.role != UserRole.EMPLOYER,
        )

        user = await self.user_repo.create_with_profile(
            user=new_user,
            first_name=user_in.first_name,
            last_name=user_in.last_name,
        )

        logger.info("User registered", user_id=str(user.id), role=str(user.role))
        return AuthResponse(**create_tokens(user.id), user=user)

    async def authenticate(self, email: str, password: str) -> AuthResponse:
        """
        Аутентифицирует пользователя по email + пароль.

        Единое сообщение об ошибке для неверного email и неверного пароля —
        намеренно, чтобы не раскрывать факт существования аккаунта (user enumeration).
        """
        user = await self.user_repo.get_by_email_with_profile(email)

        if not user or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise UserNotActiveError()

        logger.info("User authenticated", user_id=str(user.id), role=str(user.role))
        return AuthResponse(**create_tokens(user.id), user=user)

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """
        Принимает действующий refresh_token и выдаёт новую пару токенов.

        Для полноценного blacklist (инвалидации старых токенов) нужен Redis.
        Текущая реализация — stateless валидация подписи и типа токена.
        """
        payload = decode_token(refresh_token, expected_type="refresh")
        if payload is None:
            raise InvalidTokenError()

        try:
            user_id = uuid.UUID(payload["sub"])
        except (ValueError, KeyError) as e:
            raise InvalidTokenError() from e

        user = await self.user_repo.get(user_id)

        if not user:
            raise InvalidTokenError()
        if not user.is_active:
            raise UserNotActiveError()

        logger.info("Tokens refreshed", user_id=str(user_id))
        return TokenResponse(**create_tokens(user_id))
