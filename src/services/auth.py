import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from src.core.security import create_tokens, hash_password, verify_password
from src.models.user import Profile, User, UserRole
from src.schemas.user import UserCreate

logger = structlog.get_logger()


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register_new_user(self, user_in: UserCreate) -> User:
        from sqlalchemy import select

        existing_user = await self.db.execute(select(User).where(User.email == user_in.email))
        if existing_user.scalar_one_or_none():
            raise UserAlreadyExistsError()

        new_user = User(
            email=user_in.email,
            hashed_password=hash_password(user_in.password),
            role=user_in.role,
            is_verified=False if user_in.role == UserRole.EMPLOYER else True,
        )
        self.db.add(new_user)
        await self.db.flush()

        new_profile = Profile(
            user_id=new_user.id, first_name=user_in.first_name, last_name=user_in.last_name
        )
        self.db.add(new_profile)

        await self.db.commit()
        await self.db.refresh(new_user)

        logger.info("User registered", user_id=str(new_user.id), role=new_user.role)
        return new_user

    async def authenticate(self, email: str, password: str) -> dict:
        from sqlalchemy import select

        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()

        return create_tokens(user.id)
