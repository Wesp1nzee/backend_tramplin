import uuid
from datetime import UTC, datetime

import structlog
from jwt import DecodeError, ExpiredSignatureError
from jwt import InvalidTokenError as JWTInvalidTokenError
from jwt import decode as jwt_decode

from src.core.config import settings
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
from src.utils.cache import token_blacklist

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

        if await token_blacklist.is_blacklisted(refresh_token):
            logger.warning("Attempt to use blacklisted refresh token")

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

    async def logout(self, access_token: str, refresh_token: str) -> None:
        """
        Добавляет токены в blacklist для предотвращения повторного использования.

        Args:
            access_token: Access токен для добавления в blacklist
            refresh_token: Refresh токен для добавления в blacklist
        """
        try:
            access_payload = jwt_decode(
                access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            refresh_payload = jwt_decode(
                refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
        except (Exception, DecodeError, ExpiredSignatureError, JWTInvalidTokenError) as e:
            logger.warning("Invalid token in logout", error=str(e))
            raise InvalidTokenError("Invalid token provided") from e

        access_exp = datetime.fromtimestamp(access_payload["exp"], tz=UTC)
        refresh_exp = datetime.fromtimestamp(refresh_payload["exp"], tz=UTC)
        now = datetime.now(UTC)

        access_ttl = int((access_exp - now).total_seconds())
        refresh_ttl = int((refresh_exp - now).total_seconds())

        if access_ttl > 0:
            await token_blacklist.add_token(access_token, access_ttl)
        if refresh_ttl > 0:
            await token_blacklist.add_token(refresh_token, refresh_ttl)

        logger.info("User logged out, tokens blacklisted")

    async def request_password_reset(self, email: str) -> dict[str, str]:
        """
        Запрашивает сброс пароля через email.

        TODO: Реализовать отправку email с токеном сброса.
        Пока просто возвращаем успех (для разработки).
        """
        user = await self.user_repo.get_by_email(email)
        if not user:
            logger.info("Password reset requested", email_hash=self._hash_email_for_log(email))
            return {"message": "If the email exists, a reset link has been sent"}

        from datetime import timedelta

        from src.core.security import _create_token

        _create_token(
            str(user.id),
            timedelta(hours=1),
            token_type="password_reset",  # nosec B106
        )

        # TODO: Отправить email с токеном
        # await email_service.send_password_reset_email(user.email, reset_token)

        logger.info("Password reset token generated", user_id=str(user.id))
        return {"message": "If the email exists, a reset link has been sent"}

    def _hash_email_for_log(self, email: str) -> str:
        """Хеширует email для безопасного логирования"""
        import hashlib

        return hashlib.sha256(email.encode()).hexdigest()[:8]

    async def confirm_password_reset(self, token: str, new_password: str) -> dict[str, str]:
        """
        Подтверждает сброс пароля с токеном.

        Args:
            token: Токен сброса пароля из email
            new_password: Новый пароль пользователя
        """
        payload = decode_token(token, expected_type="password_reset")
        if payload is None:
            raise InvalidTokenError(detail="Invalid or expired reset token")

        try:
            user_id = uuid.UUID(payload["sub"])
        except (ValueError, KeyError) as e:
            raise InvalidTokenError(detail="Invalid reset token") from e

        user = await self.user_repo.get(user_id)
        if not user:
            raise InvalidTokenError(detail="Invalid reset token")

        user.hashed_password = hash_password(new_password)
        await self.user_repo.db.commit()

        logger.info("Password reset completed", user_id=str(user.id))
        return {"message": "Password has been reset successfully"}
