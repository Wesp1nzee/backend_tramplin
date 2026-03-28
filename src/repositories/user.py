from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.core.exceptions import RepositoryError
from src.models.skill import ProfileSkill, Skill
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

    async def search_applicants(
        self,
        *,
        skills: list[str] | None = None,
        university: str | None = None,
        graduation_year: int | None = None,
        city: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """
        Поиск соискателей по фильтрам с учётом приватности.

        Args:
            skills: Список навыков для поиска
            university: Название вуза
            graduation_year: Год выпуска
            city: Город
            limit: Лимит записей
            offset: Смещение

        Returns:
            tuple[list[User], int]: Список пользователей и общее количество

        Важно: Возвращает только пользователей с public_profile=True
        """
        try:
            # Базовый запрос с джойном профиля
            query = (
                select(User)
                .join(Profile)
                .where(
                    User.role == "applicant",
                    User.is_active,
                    Profile.privacy_settings["public_profile"].as_boolean(),
                )
            )

            # Фильтр по навыкам (через ProfileSkill)
            if skills:
                query = query.join(Profile.profile_skills).join(ProfileSkill.skill).where(Skill.name.in_(skills))

            # Фильтр по вузу
            if university:
                query = query.where(Profile.university.ilike(f"%{university}%"))

            # Фильтр по году выпуска
            if graduation_year:
                query = query.where(Profile.graduation_year == graduation_year)

            # Фильтр по городу (из профиля пользователя)
            if city:
                query = query.where(Profile.university.ilike(f"%{city}%"))

            # Получаем общее количество
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0

            # Применяем пагинацию и загружаем профиль с навыками
            query = query.options(
                selectinload(User.profile).selectinload(Profile.profile_skills).selectinload(ProfileSkill.skill)
            )
            query = query.offset(offset).limit(limit)

            result = await self.db.execute(query)
            users = result.scalars().all()

            return list(users), total
        except SQLAlchemyError as e:
            raise RepositoryError() from e
