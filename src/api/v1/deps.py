import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.security import decode_token
from src.db.session import get_db
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.user import UserRepository
from src.services.auth import AuthService
from src.services.user import UserService
from src.utils.cache import token_blacklist

__all__ = [
    "get_db",
    "get_user_repository",
    "get_auth_service",
    "get_user_service",
    "get_current_user",
    "get_current_verified_user",
    "RoleChecker",
]

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    scheme_name="JWT",
)


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(user_repo)


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repo)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(reusable_oauth2),
) -> User:
    """
    Dependency для защищённых эндпоинтов.
    Декодирует access-токен, проверяет существование и активность пользователя.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token, expected_type="access")
    if payload is None:
        raise credentials_exception

    if await token_blacklist.is_blacklisted(token):
        raise credentials_exception

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError) as e:
        raise credentials_exception from e

    result = await db.execute(
        select(User).options(selectinload(User.profile)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


async def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Расширение get_current_user: дополнительно проверяет верификацию аккаунта."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not verified",
        )
    return current_user


class RoleChecker:
    """
    Фабрика зависимостей для контроля доступа по ролям (RBAC).

    Использование:
        require_curator = RoleChecker([UserRole.CURATOR])

        @router.delete("/users/{id}", dependencies=[Depends(require_curator)])
        async def delete_user(...): ...
    """

    def __init__(self, allowed_roles: list[UserRole]) -> None:
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return user
