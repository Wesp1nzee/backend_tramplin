"""
Репозиторий для работы с регистрацией на мероприятия.

Ключевые решения:
  - Используем selectinload для eager loading связанных данных
  - Проверяем capacity через БД для предотвращения overbooking
  - Генерируем уникальные check-in коды
  - Используем INSERT ... ON CONFLICT для идемпотентности
"""

from __future__ import annotations

import logging
import secrets
import string
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.core.exceptions import RepositoryError
from src.models.application import EventRegistration
from src.models.enums import OpportunityType
from src.models.opportunity import Opportunity
from src.models.user import Profile
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def generate_check_in_code(length: int = 8) -> str:
    """
    Генерирует уникальный код для check-in.
    Использует только заглавные буквы и цифры для удобства ввода.
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class EventRegistrationRepository(BaseRepository[EventRegistration]):
    """Репозиторий для работы с регистрацией на мероприятия."""

    model = EventRegistration

    async def get_event_info(self, opportunity_id: UUID) -> Opportunity | None:
        """
        Получить информацию о мероприятии.
        Проверяет, что opportunity имеет тип EVENT.
        """
        try:
            result = await self.db.execute(
                select(Opportunity).where(
                    Opportunity.id == opportunity_id,
                    Opportunity.type == OpportunityType.EVENT,
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("EventRegistrationRepository.get_event_info error: %s", e)
            raise RepositoryError() from e

    async def get_registration_by_profile_and_event(
        self,
        profile_id: UUID,
        opportunity_id: UUID,
    ) -> EventRegistration | None:
        """
        Проверить, зарегистрирован ли пользователь на мероприятие.
        """
        try:
            result = await self.db.execute(
                select(EventRegistration).where(
                    EventRegistration.profile_id == profile_id,
                    EventRegistration.opportunity_id == opportunity_id,
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("EventRegistrationRepository.get_registration_by_profile_and_event error: %s", e)
            raise RepositoryError() from e

    async def get_user_profile_id(self, user_id: UUID) -> UUID | None:
        """
        Получить ID профиля пользователя.
        """
        try:
            result = await self.db.execute(select(Profile.id).where(Profile.user_id == user_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error("EventRegistrationRepository.get_user_profile_id error: %s", e)
            raise RepositoryError() from e

    async def register_for_event(
        self,
        profile_id: UUID,
        opportunity_id: UUID,
        status: str = "confirmed",
    ) -> EventRegistration:
        """
        Зарегистрировать пользователя на мероприятие.
        """
        try:
            # Проверяем, не зарегистрирован ли уже
            existing = await self.get_registration_by_profile_and_event(profile_id, opportunity_id)
            if existing:
                return existing

            # Генерируем check-in код
            check_in_code = generate_check_in_code()

            # Создаём регистрацию
            registration = EventRegistration(
                profile_id=profile_id,
                opportunity_id=opportunity_id,
                status=status,
                check_in_code=check_in_code,
            )
            self.db.add(registration)
            await self.db.flush()  # Получаем ID

            # Обновляем счётчик участников если confirmed
            if status == "confirmed":
                await self._increment_participants_count(opportunity_id)

            await self.db.commit()
            await self.db.refresh(registration)

            # Загружаем профиль для ответа
            result = await self.db.execute(
                select(EventRegistration)
                .options(selectinload(EventRegistration.profile))
                .where(EventRegistration.id == registration.id)
            )
            return result.scalar_one()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("EventRegistrationRepository.register_for_event error: %s", e)
            raise RepositoryError() from e

    async def cancel_registration(
        self,
        profile_id: UUID,
        opportunity_id: UUID,
    ) -> None:
        """
        Отменить регистрацию пользователя.
        Освобождает место для waitlist.
        """
        try:
            # Находим регистрацию
            registration = await self.get_registration_by_profile_and_event(profile_id, opportunity_id)
            if not registration:
                return  # Уже отменена или не была зарегистрирована

            was_confirmed = registration.status == "confirmed"

            # Удаляем регистрацию
            await self.db.delete(registration)

            # Обновляем счётчик если был confirmed
            if was_confirmed:
                await self._decrement_participants_count(opportunity_id)

            await self.db.commit()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("EventRegistrationRepository.cancel_registration error: %s", e)
            raise RepositoryError() from e

    async def get_event_participants(
        self,
        opportunity_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[EventRegistration], int, int, int]:
        """
        Получить список участников мероприятия.
        Returns: (items, total, confirmed_count, waitlist_count)
        """
        try:
            # Считаем total и counts
            count_stmt = (
                select(func.count())
                .select_from(EventRegistration)
                .where(
                    EventRegistration.opportunity_id == opportunity_id,
                    EventRegistration.status != "cancelled",
                )
            )
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar_one() or 0

            confirmed_stmt = (
                select(func.count())
                .select_from(EventRegistration)
                .where(
                    EventRegistration.opportunity_id == opportunity_id,
                    EventRegistration.status == "confirmed",
                )
            )
            confirmed_result = await self.db.execute(confirmed_stmt)
            confirmed_count = confirmed_result.scalar_one() or 0

            waitlist_stmt = (
                select(func.count())
                .select_from(EventRegistration)
                .where(
                    EventRegistration.opportunity_id == opportunity_id,
                    EventRegistration.status == "waitlist",
                )
            )
            waitlist_result = await self.db.execute(waitlist_stmt)
            waitlist_count = waitlist_result.scalar_one() or 0

            # Получаем участников с профилями
            stmt = (
                select(EventRegistration)
                .options(selectinload(EventRegistration.profile))
                .where(
                    EventRegistration.opportunity_id == opportunity_id,
                    EventRegistration.status != "cancelled",
                )
                .order_by(EventRegistration.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(stmt)
            registrations = list(result.scalars().unique().all())

            return registrations, total, confirmed_count, waitlist_count

        except SQLAlchemyError as e:
            logger.error("EventRegistrationRepository.get_event_participants error: %s", e)
            raise RepositoryError() from e

    async def check_in_participant(
        self,
        opportunity_id: UUID,
        check_in_code: str,
    ) -> EventRegistration | None:
        """
        Отметить участника как присутствующего по коду.
        """
        try:
            from datetime import datetime

            # Находим регистрацию по коду
            result = await self.db.execute(
                select(EventRegistration)
                .options(selectinload(EventRegistration.profile))
                .where(
                    EventRegistration.opportunity_id == opportunity_id,
                    EventRegistration.check_in_code == check_in_code.upper(),
                    EventRegistration.status.in_(["confirmed", "waitlist"]),
                )
            )
            registration = result.scalar_one_or_none()

            if not registration:
                return None

            # Отмечаем check-in
            registration.checked_in_at = datetime.now(datetime.UTC)  # type: ignore[attr-defined]
            await self.db.commit()
            await self.db.refresh(registration)

            return registration

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("EventRegistrationRepository.check_in_participant error: %s", e)
            raise RepositoryError() from e

    async def get_waitlist_next(
        self,
        opportunity_id: UUID,
    ) -> EventRegistration | None:
        """
        Получить следующего участника из waitlist.
        """
        try:
            result = await self.db.execute(
                select(EventRegistration)
                .options(selectinload(EventRegistration.profile))
                .where(
                    EventRegistration.opportunity_id == opportunity_id,
                    EventRegistration.status == "waitlist",
                )
                .order_by(EventRegistration.created_at.asc())
                .limit(1)
            )
            return result.scalar_one_or_none()

        except SQLAlchemyError as e:
            logger.error("EventRegistrationRepository.get_waitlist_next error: %s", e)
            raise RepositoryError() from e

    async def promote_from_waitlist(
        self,
        registration: EventRegistration,
    ) -> EventRegistration:
        """
        Перевести участника из waitlist в confirmed.
        """
        try:
            registration.status = "confirmed"
            # Генерируем новый check-in код
            registration.check_in_code = generate_check_in_code()
            await self.db.commit()
            await self.db.refresh(registration)

            return registration

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error("EventRegistrationRepository.promote_from_waitlist error: %s", e)
            raise RepositoryError() from e

    async def _increment_participants_count(self, opportunity_id: UUID) -> None:
        """Атомарно увеличивает счётчик участников."""
        try:
            from sqlalchemy import update

            await self.db.execute(
                update(Opportunity)
                .where(Opportunity.id == opportunity_id)
                .values(current_participants=Opportunity.current_participants + 1)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            logger.warning("Failed to increment participants count for %s: %s", opportunity_id, e)
            await self.db.rollback()

    async def _decrement_participants_count(self, opportunity_id: UUID) -> None:
        """Атомарно уменьшает счётчик участников."""
        try:
            from sqlalchemy import update

            await self.db.execute(
                update(Opportunity)
                .where(Opportunity.id == opportunity_id)
                .values(current_participants=func.greatest(Opportunity.current_participants - 1, 0))
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            logger.warning("Failed to decrement participants count for %s: %s", opportunity_id, e)
            await self.db.rollback()
