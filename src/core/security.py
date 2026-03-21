import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt  # Используем PyJWT
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError, PyJWTError

from src.core.config import settings

ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Хеширует пароль через Argon2id (без лимита 72 байта)."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет пароль, возвращая False при любой ошибке валидации."""
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError, Exception:
        return False


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    """Внутренний конструктор JWT через PyJWT."""
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": subject,
        "exp": expire,
        "type": token_type,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_tokens(user_id: uuid.UUID | str) -> dict[str, str]:
    """Генерирует пару токенов: access + refresh."""
    return {
        "access_token": _create_token(
            str(user_id),
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            token_type="access",
        ),
        "refresh_token": _create_token(
            str(user_id),
            timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
            token_type="refresh",
        ),
        "token_type": "bearer",
    }


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any] | None:
    """
    Декодирует JWT.
    Использует алиас JWTError для совместимости с вызывающим кодом.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except PyJWTError, ExpiredSignatureError, InvalidTokenError:
        return None

    if payload.get("type") != expected_type:
        return None
    if not payload.get("sub"):
        return None

    return payload
