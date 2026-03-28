"""
Сервис для работы с рекомендациями.

Бизнес-логика:
  - Проверка связи между пользователями (Contact status = ACCEPTED)
  - Валидация вакансии (ACTIVE статус)
  - Валидация получателя (должен быть APPLICANT)
  - Создание уведомлений
"""

import logging
from typing import Any
from uuid import UUID

from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.models.enums import NotificationType, OpportunityStatus, UserRole
from src.models.notification import Notification
from src.models.opportunity import Opportunity
from src.repositories.recommendation import RecommendationRepository

logger = logging.getLogger(__name__)


class RecommendationService:
    """
    Бизнес-логика системы рекомендаций.

    Отвечает за:
      - Создание рекомендаций между контактами
      - Валидацию связей и прав доступа
      - Управление уведомлениями
    """

    def __init__(self, recommendation_repo: RecommendationRepository) -> None:
        self.recommendation_repo = recommendation_repo

    async def create_recommendation(
        self,
        sender_id: UUID,
        recipient_id: UUID,
        opportunity_id: UUID,
        message: str | None = None,
    ) -> dict[str, Any]:
        """
        Создать рекомендацию вакансии.

        Проверки:
          - Отправитель и получатель не могут быть одним лицом
          - Между пользователями должна быть связь (Contact ACCEPTED)
          - Вакансия должна быть ACTIVE
          - Получатель должен быть APPLICANT

        Args:
            sender_id: ID отправителя (пользователь)
            recipient_id: ID получателя (пользователь)
            opportunity_id: ID вакансии
            message: Опциональное сообщение

        Returns:
            dict: Данные созданной рекомендации

        Raises:
            PermissionDeniedError: Если нет связи или рекомендация самому себе
            NotFoundError: Если вакансия или пользователь не найдены
        """
        # Проверка: рекомендация самому себе
        if sender_id == recipient_id:
            raise PermissionDeniedError(detail="Cannot recommend a vacancy to yourself")

        # Получаем профили отправителя и получателя
        sender_profile = await self.recommendation_repo.get_profile_by_user_id(sender_id)
        recipient_profile = await self.recommendation_repo.get_profile_by_user_id(recipient_id)

        if not sender_profile:
            raise NotFoundError(detail="Sender profile not found")

        if not recipient_profile:
            raise NotFoundError(detail="Recipient profile not found")

        # Проверка: получатель должен быть APPLICANT
        recipient_role = await self.recommendation_repo.get_user_role(recipient_id)
        if recipient_role != UserRole.APPLICANT:
            raise PermissionDeniedError(detail="Can only recommend vacancies to applicants")

        # Проверка: наличие связи ACCEPTED между пользователями
        has_contact = await self.recommendation_repo.check_contact_relationship(
            sender_id=sender_id,
            recipient_id=recipient_id,
        )
        if not has_contact:
            raise PermissionDeniedError(detail="You can only recommend vacancies to your accepted contacts")

        # Проверка: вакансия должна существовать и быть ACTIVE
        opportunity = await self.recommendation_repo.db.get(Opportunity, opportunity_id)
        if not opportunity:
            raise NotFoundError(detail="Opportunity not found")

        if opportunity.status != OpportunityStatus.ACTIVE:
            from src.core.exceptions import OpportunityNotActiveError

            raise OpportunityNotActiveError()

        # Создаём рекомендацию
        recommendation = await self.recommendation_repo.create_recommendation(
            sender_id=sender_profile.id,
            recipient_id=recipient_profile.id,
            opportunity_id=opportunity_id,
            message=message,
        )

        # Создаём уведомление для получателя
        await self._create_recommendation_notification(
            recipient_id=recipient_id,
            sender_id=sender_id,
            opportunity_id=opportunity_id,
            recommendation_id=recommendation.id,
        )

        return {
            "id": recommendation.id,
            "sender_id": sender_profile.id,
            "recipient_id": recipient_profile.id,
            "opportunity_id": opportunity_id,
            "message": message,
            "is_read": False,
        }

    async def get_sent_recommendations(
        self,
        sender_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Any], int]:
        """
        Получить список отправленных рекомендаций.

        Args:
            sender_id: ID отправителя (пользователь)
            limit: Лимит записей
            offset: Смещение

        Returns:
            tuple[list, int]: Список рекомендаций и общее количество
        """
        # Получаем профиль отправителя
        sender_profile = await self.recommendation_repo.get_profile_by_user_id(sender_id)
        if not sender_profile:
            raise NotFoundError(detail="Sender profile not found")

        recommendations, total = await self.recommendation_repo.get_sent_recommendations(
            sender_id=sender_profile.id,
            limit=limit,
            offset=offset,
        )

        return recommendations, total

    async def get_received_recommendations(
        self,
        recipient_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Any], int]:
        """
        Получить список полученных рекомендаций.

        Args:
            recipient_id: ID получателя (пользователь)
            limit: Лимит записей
            offset: Смещение

        Returns:
            tuple[list, int]: Список рекомендаций и общее количество
        """
        # Получаем профиль получателя
        recipient_profile = await self.recommendation_repo.get_profile_by_user_id(recipient_id)
        if not recipient_profile:
            raise NotFoundError(detail="Recipient profile not found")

        recommendations, total = await self.recommendation_repo.get_received_recommendations(
            recipient_id=recipient_profile.id,
            limit=limit,
            offset=offset,
        )

        return recommendations, total

    async def mark_recommendation_as_read(
        self,
        recommendation_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        Отметить рекомендацию как прочитанную.

        Args:
            recommendation_id: ID рекомендации
            user_id: ID текущего пользователя (для проверки прав)

        Returns:
            dict: Данные обновлённой рекомендации

        Raises:
            NotFoundError: Если рекомендация не найдена
            PermissionDeniedError: Если пользователь не получатель
        """
        recommendation = await self.recommendation_repo.get_recommendation_with_relations(recommendation_id=recommendation_id)

        if not recommendation:
            raise NotFoundError(detail="Recommendation not found")

        # Проверка: только получатель может отметить как прочитанное
        recipient_user_id = await self._get_user_id_from_profile(recommendation.recipient_id)
        if recipient_user_id != user_id:
            raise PermissionDeniedError(detail="Only the recipient can mark recommendation as read")

        updated = await self.recommendation_repo.mark_as_read(recommendation)

        return {
            "id": updated.id,
            "is_read": updated.is_read,
            "updated_at": updated.updated_at,
        }

    async def _create_recommendation_notification(
        self,
        recipient_id: UUID,
        sender_id: UUID,
        opportunity_id: UUID,
        recommendation_id: UUID,
    ) -> None:
        """
        Создать уведомление о рекомендации.

        Args:
            recipient_id: ID получателя (пользователь)
            sender_id: ID отправителя (пользователь)
            opportunity_id: ID вакансии
            recommendation_id: ID рекомендации
        """
        try:
            # Получаем данные для уведомления
            sender_profile = await self.recommendation_repo.get_profile_by_user_id(sender_id)
            opportunity = await self.recommendation_repo.db.get(Opportunity, opportunity_id)

            if not sender_profile or not opportunity:
                logger.warning("Failed to create recommendation notification: missing data")
                return

            notification = Notification(
                recipient_id=recipient_id,
                type=NotificationType.RECOMMENDATION,
                title="Рекомендация вакансии",
                body=f"{sender_profile.first_name} {sender_profile.last_name} рекомендует вам вакансию «{opportunity.title}»",
                payload={
                    "type": "recommendation",
                    "id": str(recommendation_id),
                    "opportunity_id": str(opportunity_id),
                    "url": f"/recommendations/{recommendation_id}",
                },
            )
            self.recommendation_repo.db.add(notification)
            await self.recommendation_repo.db.commit()
        except Exception as e:
            logger.error("Failed to create recommendation notification: %s", e)
            # Не пробрасываем ошибку — уведомление не должно ломать создание рекомендации

    async def _get_user_id_from_profile(self, profile_id: UUID) -> UUID | None:
        """
        Получить ID пользователя по ID профиля.

        Args:
            profile_id: ID профиля

        Returns:
            UUID | None: ID пользователя или None
        """
        from sqlalchemy import select

        from src.models.user import Profile

        result = await self.recommendation_repo.db.execute(select(Profile.user_id).where(Profile.id == profile_id))
        return result.scalar_one_or_none()
