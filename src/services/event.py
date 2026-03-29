"""
Бизнес-логика для регистрации на мероприятия.

Сервис отвечает за:
  - Регистрацию на мероприятия с проверкой capacity
  - Управление waitlist
  - Check-in участников
  - Отправку уведомлений работодателю
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import (
    EventNotActiveError,
    EventNotEventTypeError,
    EventRegistrationAlreadyExistsError,
    NotFoundError,
)
from src.models.enums import NotificationType, OpportunityStatus
from src.models.notification import Notification
from src.models.user import Profile, User
from src.repositories.event import EventRegistrationRepository
from src.repositories.opportunity import OpportunityRepository
from src.schemas.event import (
    EventCheckInResponse,
    EventInfo,
    EventRegistrationItem,
    EventRegistrationListResponse,
    EventRegistrationResponse,
)
from src.schemas.user import ApplicantProfileShort

logger = logging.getLogger(__name__)


class EventService:
    """Сервис для работы с регистрацией на мероприятия."""

    def __init__(
        self,
        event_repo: EventRegistrationRepository,
        opportunity_repo: OpportunityRepository,
    ) -> None:
        self.event_repo = event_repo
        self.opportunity_repo = opportunity_repo

    async def get_event_info(
        self,
        opportunity_id: UUID,
        user_id: UUID | None = None,
    ) -> EventInfo:
        """
        Получить информацию о мероприятии для регистрации.
        """
        event = await self.event_repo.get_event_info(opportunity_id)
        if not event:
            raise EventNotEventTypeError()

        # Проверяем статус
        if event.status != OpportunityStatus.ACTIVE:
            raise EventNotActiveError()

        # Проверяем регистрацию пользователя
        user_registration_status = None
        if user_id:
            profile_id = await self.event_repo.get_user_profile_id(user_id)
            if profile_id:
                registration = await self.event_repo.get_registration_by_profile_and_event(profile_id, opportunity_id)
                if registration:
                    user_registration_status = registration.status

        # Считаем доступные места
        available_spots = None
        if event.max_participants is not None:
            available_spots = max(0, event.max_participants - event.current_participants)

        return EventInfo(
            id=event.id,
            title=event.title,
            event_start_at=event.event_start_at,
            event_end_at=event.event_end_at,
            max_participants=event.max_participants,
            current_participants=event.current_participants,
            available_spots=available_spots,
            user_registration_status=user_registration_status,
        )

    async def register_for_event(
        self,
        opportunity_id: UUID,
        user: User,
    ) -> EventRegistrationResponse:
        """
        Зарегистрировать пользователя на мероприятие.
        """
        # Проверяем, что это мероприятие
        event = await self.event_repo.get_event_info(opportunity_id)
        if not event:
            raise EventNotEventTypeError()

        # Проверяем статус
        if event.status != OpportunityStatus.ACTIVE:
            raise EventNotActiveError()

        # Получаем профиль пользователя
        profile_id = await self.event_repo.get_user_profile_id(user.id)
        if not profile_id:
            raise NotFoundError(detail="User profile not found. Please complete your profile first.")

        # Проверяем, не зарегистрирован ли уже
        existing = await self.event_repo.get_registration_by_profile_and_event(profile_id, opportunity_id)
        if existing and existing.status != "cancelled":
            raise EventRegistrationAlreadyExistsError()

        # Проверяем capacity
        has_capacity = event.max_participants is None or event.current_participants < event.max_participants

        if has_capacity:
            status = "confirmed"
            message = "Successfully registered for the event"
        else:
            status = "waitlist"
            message = "Event is full. You have been added to the waitlist"

        # Регистрируем
        registration = await self.event_repo.register_for_event(
            profile_id=profile_id,
            opportunity_id=opportunity_id,
            status=status,
        )

        # Создаём уведомление работодателю
        await self._create_registration_notification(
            employer_id=event.company.owner_id,
            event_id=opportunity_id,
            user_id=user.id,
            user_name=f"{user.profile.first_name} {user.profile.last_name}" if user.profile else "User",
            registration_status=status,
        )

        return EventRegistrationResponse(
            id=registration.id,
            status=status,
            message=message,
            check_in_code=registration.check_in_code if status == "confirmed" else None,
            event_id=opportunity_id,
        )

    async def cancel_registration(
        self,
        opportunity_id: UUID,
        user: User,
    ) -> EventRegistrationResponse:
        """
        Отменить регистрацию пользователя.
        """
        # Получаем профиль
        profile_id = await self.event_repo.get_user_profile_id(user.id)
        if not profile_id:
            raise NotFoundError(detail="User profile not found")

        # Проверяем регистрацию
        registration = await self.event_repo.get_registration_by_profile_and_event(profile_id, opportunity_id)
        if not registration:
            raise NotFoundError(detail="You are not registered for this event")

        # Запоминаем статус перед удалением
        was_confirmed = registration.status == "confirmed"

        # Отменяем регистрацию
        await self.event_repo.cancel_registration(
            profile_id=profile_id,
            opportunity_id=opportunity_id,
        )

        # Если был confirmed, продвигаем кого-то из waitlist
        if was_confirmed:
            await self._promote_next_from_waitlist(opportunity_id)

        return EventRegistrationResponse(
            id=registration.id,
            status="cancelled",
            message="Registration cancelled successfully",
            event_id=opportunity_id,
        )

    async def get_participants(
        self,
        opportunity_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> EventRegistrationListResponse:
        """
        Получить список участников мероприятия.
        """
        registrations, total, confirmed_count, waitlist_count = await self.event_repo.get_event_participants(
            opportunity_id=opportunity_id,
            limit=limit,
            offset=offset,
        )

        items = [
            EventRegistrationItem(
                id=reg.id,
                profile=self._to_profile_short(reg.profile),
                status=reg.status,
                check_in_code=reg.check_in_code,
                checked_in_at=reg.checked_in_at,
                registered_at=reg.created_at,
            )
            for reg in registrations
        ]

        return EventRegistrationListResponse(
            items=items,
            total=total,
            confirmed_count=confirmed_count,
            waitlist_count=waitlist_count,
        )

    async def check_in_participant(
        self,
        opportunity_id: UUID,
        check_in_code: str,
        checker_user: User,
    ) -> EventCheckInResponse:
        """
        Отметить участника как присутствующего по коду.
        """
        # Проверяем, что это мероприятие
        event = await self.event_repo.get_event_info(opportunity_id)
        if not event:
            raise EventNotEventTypeError()

        # Находим регистрацию по коду
        registration = await self.event_repo.check_in_participant(
            opportunity_id=opportunity_id,
            check_in_code=check_in_code,
        )

        if not registration:
            raise NotFoundError(detail="Invalid check-in code or registration not found")

        return EventCheckInResponse(
            success=True,
            message=f"Checked in: {registration.profile.first_name} {registration.profile.last_name}",
            profile_id=registration.profile.id,
            checked_in_at=registration.checked_in_at,
        )

    async def _promote_next_from_waitlist(self, opportunity_id: UUID) -> None:
        """
        Продвинуть следующего участника из waitlist.
        """
        try:
            # Получаем следующего из waitlist
            next_in_line = await self.event_repo.get_waitlist_next(opportunity_id)
            if next_in_line:
                # Продвигаем
                await self.event_repo.promote_from_waitlist(next_in_line)

                # Создаём уведомление
                await self._create_spot_available_notification(
                    user_id=next_in_line.profile.user_id,
                    event_id=opportunity_id,
                )
        except Exception as e:
            logger.error("Failed to promote from waitlist: %s", e)

    async def _create_registration_notification(
        self,
        employer_id: UUID,
        event_id: UUID,
        user_id: UUID,
        user_name: str,
        registration_status: str,
    ) -> None:
        """
        Создать уведомление работодателю о новой регистрации.
        """
        title = "Новая регистрация на мероприятие"
        body = (
            f"{user_name} зарегистрировался на ваше мероприятие."
            if registration_status == "confirmed"
            else f"{user_name} добавлен в лист ожидания."
        )

        notification = Notification(
            recipient_id=employer_id,
            type=NotificationType.NEW_APPLICATION,  # Используем аналогичный тип
            title=title,
            body=body,
            payload={
                "type": "event_registration",
                "event_id": str(event_id),
                "user_id": str(user_id),
                "status": registration_status,
            },
        )

        self.event_repo.db.add(notification)
        try:
            await self.event_repo.db.commit()
        except SQLAlchemyError as e:
            logger.error("Failed to create registration notification: %s", e)
            await self.event_repo.db.rollback()

    async def _create_spot_available_notification(
        self,
        user_id: UUID,
        event_id: UUID,
    ) -> None:
        """
        Создать уведомление пользователю о доступном месте.
        """
        notification = Notification(
            recipient_id=user_id,
            type=NotificationType.SYSTEM,
            title="Доступно место на мероприятии",
            body="Появилось свободное место на мероприятии. Вы переведены из листа ожидания в подтверждённые участники.",
            payload={
                "type": "event_spot_available",
                "event_id": str(event_id),
            },
        )

        self.event_repo.db.add(notification)
        try:
            await self.event_repo.db.commit()
        except SQLAlchemyError as e:
            logger.error("Failed to create spot available notification: %s", e)
            await self.event_repo.db.rollback()

    @staticmethod
    def _to_profile_short(profile: Profile) -> ApplicantProfileShort:
        """Конвертирует ORM-модель профиля в DTO."""

        # Извлекаем названия навыков из relationship
        skills = [ps.skill.name for ps in profile.profile_skills if ps.skill] if profile.profile_skills else []

        return ApplicantProfileShort(
            id=profile.id,
            first_name=profile.first_name,
            last_name=profile.last_name,
            middle_name=profile.middle_name,
            university=profile.university,
            graduation_year=profile.graduation_year,
            headline=profile.headline,
            bio=profile.bio,
            avatar_url=profile.avatar_url,
            phone=profile.phone,
            social_links=profile.social_links or {},
            portfolio_url=profile.portfolio_url,
            cv_url=profile.cv_url,
            skills=skills,
            privacy_settings=profile.privacy_settings or {},
            career_preferences=profile.career_preferences or {},
            show_full_data=False,
        )
