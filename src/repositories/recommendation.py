"""
Репозиторий для работы с рекомендациями.

Recommendation - рекомендация вакансии от одного соискателя другому.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.core.exceptions import RepositoryError
from src.models.social import Contact, Recommendation
from src.models.user import Profile
from src.repositories.base import BaseRepository


class RecommendationRepository(BaseRepository[Recommendation]):
    """
    Репозиторий для операций с рекомендациями.
    """

    model = Recommendation

    async def create_recommendation(
        self,
        sender_id: UUID,
        recipient_id: UUID,
        opportunity_id: UUID,
        message: str | None = None,
    ) -> Recommendation:
        """
        Создать рекомендацию.

        Args:
            sender_id: ID отправителя (профиль)
            recipient_id: ID получателя (профиль)
            opportunity_id: ID вакансии
            message: Опциональное сообщение

        Returns:
            Recommendation: Созданная рекомендация
        """
        try:
            recommendation = Recommendation(
                sender_id=sender_id,
                recipient_id=recipient_id,
                opportunity_id=opportunity_id,
                message=message,
                is_read=False,
            )
            self.db.add(recommendation)
            await self.db.flush()
            await self.db.refresh(recommendation)
            return recommendation
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_recommendation_with_relations(
        self,
        recommendation_id: UUID,
    ) -> Recommendation | None:
        """
        Получить рекомендацию с загруженными связями.

        Args:
            recommendation_id: ID рекомендации

        Returns:
            Recommendation с загруженными sender, recipient, opportunity
        """
        try:
            result = await self.db.execute(
                select(Recommendation)
                .options(
                    selectinload(Recommendation.sender),
                    selectinload(Recommendation.recipient),
                    selectinload(Recommendation.opportunity),
                )
                .where(Recommendation.id == recommendation_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_sent_recommendations(
        self,
        sender_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Recommendation], int]:
        """
        Получить список отправленных рекомендаций.

        Args:
            sender_id: ID отправителя (профиль)
            limit: Лимит записей
            offset: Смещение

        Returns:
            tuple[list[Recommendation], int]: Список рекомендаций и общее количество
        """
        try:
            # Базовый запрос
            query = select(Recommendation).where(Recommendation.sender_id == sender_id)

            # Получаем общее количество
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0

            # Применяем пагинацию и загружаем связи
            query = query.options(
                selectinload(Recommendation.recipient),
                selectinload(Recommendation.opportunity),
            )
            query = query.order_by(Recommendation.created_at.desc())
            query = query.offset(offset).limit(limit)

            result = await self.db.execute(query)
            recommendations = result.scalars().all()

            return list(recommendations), total
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_received_recommendations(
        self,
        recipient_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Recommendation], int]:
        """
        Получить список полученных рекомендаций.

        Args:
            recipient_id: ID получателя (профиль)
            limit: Лимит записей
            offset: Смещение

        Returns:
            tuple[list[Recommendation], int]: Список рекомендаций и общее количество
        """
        try:
            # Базовый запрос
            query = select(Recommendation).where(Recommendation.recipient_id == recipient_id)

            # Получаем общее количество
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0

            # Применяем пагинацию и загружаем связи
            query = query.options(
                selectinload(Recommendation.sender),
                selectinload(Recommendation.opportunity),
            )
            query = query.order_by(Recommendation.created_at.desc())
            query = query.offset(offset).limit(limit)

            result = await self.db.execute(query)
            recommendations = result.scalars().all()

            return list(recommendations), total
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def mark_as_read(self, recommendation: Recommendation) -> Recommendation:
        """
        Отметить рекомендацию как прочитанную.

        Args:
            recommendation: Объект рекомендации

        Returns:
            Recommendation: Обновлённая рекомендация
        """
        try:
            recommendation.is_read = True
            await self.db.flush()
            await self.db.refresh(recommendation)
            return recommendation
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def check_contact_relationship(
        self,
        sender_id: UUID,
        recipient_id: UUID,
    ) -> bool:
        """
        Проверить наличие принятой связи между пользователями.

        Args:
            sender_id: ID отправителя (пользователь)
            recipient_id: ID получателя (пользователь)

        Returns:
            bool: True если есть связь со статусом ACCEPTED
        """
        try:
            # Проверяем наличие связи в любом направлении со статусом ACCEPTED
            result = await self.db.execute(
                select(Contact).where(
                    (
                        ((Contact.requester_id == sender_id) & (Contact.addressee_id == recipient_id))
                        | ((Contact.requester_id == recipient_id) & (Contact.addressee_id == sender_id))
                    )
                    & (Contact.status == "accepted")
                )
            )
            contact = result.scalar_one_or_none()
            return contact is not None
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_profile_by_user_id(self, user_id: UUID) -> Profile | None:
        """
        Получить профиль по ID пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            Profile: Профиль пользователя или None
        """
        try:
            result = await self.db.execute(select(Profile).where(Profile.user_id == user_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def get_user_role(self, user_id: UUID) -> str | None:
        """
        Получить роль пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            str | None: Роль пользователя или None
        """
        try:
            from src.models.user import User

            result = await self.db.execute(select(User.role).where(User.id == user_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e
