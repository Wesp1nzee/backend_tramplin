from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

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
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_with_profile(self, user_id: UUID) -> User | None:
        """Загрузить пользователя вместе с профилем (один запрос через JOIN)."""
        result = await self.db.execute(
            select(User).options(selectinload(User.profile)).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email_with_profile(self, email: str) -> User | None:
        """Найти пользователя по email вместе с профилем."""
        result = await self.db.execute(
            select(User).options(selectinload(User.profile)).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """
        Проверить занятость email.
        Делаем SELECT только на id — дешевле чем тянуть весь объект.
        """
        result = await self.db.execute(select(User.id).where(User.email == email))
        return result.scalar_one_or_none() is not None

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
        self.db.add(user)
        await self.db.flush()  # Получаем user.id до commit

        profile = Profile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
        )
        self.db.add(profile)
        await self.db.commit()

        # После commit сессия detach объекты — перезагружаем с профилем
        refreshed = await self.get_with_profile(user.id)
        assert refreshed is not None  # noqa: S101 — только что создали
        return refreshed
