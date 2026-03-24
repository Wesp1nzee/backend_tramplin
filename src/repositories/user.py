from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.core.exceptions import RepositoryError
from src.models.skill import ProfileSkill
from src.models.user import Profile, User
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Все операции с таблицами users и profiles.
    Сервисный слой не должен знать про SQL — только про этот класс.
    """

    model = User

    async def get_by_email(self, email: str) -> User | None:
        """Найти пользователя по email (без профиля)."""
        try:
            result = await self.db.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_with_profile(self, user_id: UUID) -> User | None:
        """Загрузить пользователя вместе с профилем (один запрос через JOIN)."""
        try:
            result = await self.db.execute(
                select(User)
                .options(selectinload(User.profile).selectinload(Profile.profile_skills).selectinload(ProfileSkill.skill))
                .where(User.id == user_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_by_email_with_profile(self, email: str) -> User | None:
        """Найти пользователя по email вместе с профилем."""
        try:
            result = await self.db.execute(select(User).options(selectinload(User.profile)).where(User.email == email))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def email_exists(self, email: str) -> bool:
        """
        Проверить занятость email.
        Делаем SELECT только на id — дешевле чем тянуть весь объект.
        """
        try:
            result = await self.db.execute(select(User.id).where(User.email == email))
            return result.scalar_one_or_none() is not None
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def create_with_profile(
        self,
        user: User,
        first_name: str,
        last_name: str,
    ) -> User:
        """
        Атомарно создаёт пользователя и его профиль в одной транзакции.
        Возвращает пользователя с уже загруженным профилем.
        """
        try:
            self.db.add(user)
            await self.db.flush()

            profile = Profile(
                user_id=user.id,
                first_name=first_name,
                last_name=last_name,
            )
            self.db.add(profile)
            await self.db.commit()

            refreshed = await self.get_with_profile(user.id)
            if refreshed is None:
                raise RepositoryError(detail="Failed to retrieve created user with profile")
            return refreshed
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RepositoryError() from e
