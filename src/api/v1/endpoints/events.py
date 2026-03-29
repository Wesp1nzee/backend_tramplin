"""
Эндпоинты для регистрации на мероприятия.

Для авторизованных пользователей (APPLICANT):
  - POST   /api/v1/events/{opportunity_id}/register       → регистрация на мероприятие
  - DELETE /api/v1/events/{opportunity_id}/register       → отмена регистрации
  - GET    /api/v1/events/{opportunity_id}/info           → информация о мероприятии

Для работодателей и кураторов (EMPLOYER, CURATOR):
  - GET    /api/v1/events/{opportunity_id}/participants   → список участников
  - POST   /api/v1/events/{opportunity_id}/check-in       → отметка присутствия по коду
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import RoleChecker, get_current_user_optional, get_db
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.event import EventRegistrationRepository
from src.repositories.opportunity import OpportunityRepository
from src.schemas.event import (
    EventCheckInRequest,
    EventCheckInResponse,
    EventInfo,
    EventRegistrationListResponse,
    EventRegistrationResponse,
)
from src.services.event import EventService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["Events"])


# ─── Dependency injection ─────────────────────────────────────


async def get_event_service(db: AsyncSession = Depends(get_db)) -> EventService:
    return EventService(
        event_repo=EventRegistrationRepository(db),
        opportunity_repo=OpportunityRepository(db),
    )


# ─── RBAC: Проверка ролей ─────────────────────────────────────

require_applicant = RoleChecker([UserRole.APPLICANT])
require_employer_or_curator = RoleChecker([UserRole.EMPLOYER, UserRole.CURATOR])


# ─── Public endpoints (Event Info) ────────────────────────────


@router.get(
    "/{opportunity_id}/info",
    response_model=EventInfo,
    status_code=status.HTTP_200_OK,
    summary="Информация о мероприятии",
    description=(
        "Получение информации о мероприятии для регистрации.\n\n"
        "**Доступно:** Все авторизованные пользователи\n\n"
        "Возвращает:\n"
        "- Основная информация (название, даты)\n"
        "- Максимальное количество участников\n"
        "- Текущее количество зарегистрированных\n"
        "- Доступные места\n"
        "- Статус регистрации текущего пользователя (если есть)\n\n"
        "**Проверки:**\n"
        "- Opportunity должно иметь тип EVENT\n"
        "- Статус должен быть ACTIVE"
    ),
)
async def get_event_info(
    opportunity_id: str,
    current_user: User | None = Depends(get_current_user_optional),
    event_service: EventService = Depends(get_event_service),
) -> EventInfo:
    """
    Получить информацию о мероприятии.
    """
    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    return await event_service.get_event_info(
        opportunity_id=opp_uuid,
        user_id=current_user.id if current_user else None,
    )


# ─── Applicant endpoints (Registration) ───────────────────────


@router.post(
    "/{opportunity_id}/register",
    response_model=EventRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация на мероприятие",
    description=(
        "Регистрация соискателя на карьерное мероприятие.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "**Логика:**\n"
        "- Если есть свободные места → статус `confirmed`\n"
        "- Если мест нет → статус `waitlist` (лист ожидания)\n"
        "- Генерируется уникальный `check_in_code` для отметки присутствия\n"
        "- Работодатель получает уведомление о новой регистрации\n\n"
        "**Проверки:**\n"
        "- Opportunity должно иметь тип EVENT\n"
        "- Статус должен быть ACTIVE\n"
        "- Пользователь не должен быть уже зарегистрирован\n"
        "- У пользователя должен быть заполнен профиль"
    ),
)
async def register_for_event(
    opportunity_id: str,
    current_user: User = Depends(require_applicant),
    event_service: EventService = Depends(get_event_service),
) -> EventRegistrationResponse:
    """
    Зарегистрироваться на мероприятие.
    """
    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    return await event_service.register_for_event(
        opportunity_id=opp_uuid,
        user=current_user,
    )


@router.delete(
    "/{opportunity_id}/register",
    response_model=EventRegistrationResponse,
    status_code=status.HTTP_200_OK,
    summary="Отмена регистрации",
    description=(
        "Отмена регистрации на мероприятие.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "**Логика:**\n"
        "- Освобождает место для участников из waitlist\n"
        "- Следующий участник из waitlist автоматически переводится в confirmed\n"
        "- Продвинутый участник получает уведомление\n\n"
        "**Проверки:**\n"
        "- Пользователь должен быть зарегистрирован"
    ),
)
async def cancel_registration(
    opportunity_id: str,
    current_user: User = Depends(require_applicant),
    event_service: EventService = Depends(get_event_service),
) -> EventRegistrationResponse:
    """
    Отменить регистрацию на мероприятие.
    """
    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    return await event_service.cancel_registration(
        opportunity_id=opp_uuid,
        user=current_user,
    )


# ─── Employer/Curator endpoints (Participants Management) ─────


@router.get(
    "/{opportunity_id}/participants",
    response_model=EventRegistrationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список участников мероприятия",
    description=(
        "Получение списка зарегистрированных участников мероприятия.\n\n"
        "**Требуемая роль:** EMPLOYER или CURATOR\n\n"
        "Возвращает:\n"
        "- Список участников с профилями\n"
        "- Статус регистрации (confirmed/waitlist)\n"
        "- Check-in код (для работодателя)\n"
        "- Статус отметки присутствия (checked_in_at)\n"
        "- Общее количество, confirmed_count, waitlist_count\n\n"
        "**Пагинация:**\n"
        "- `limit` — количество записей (по умолчанию 100)\n"
        "- `offset` — смещение"
    ),
)
async def get_participants(
    opportunity_id: str,
    limit: int = Query(default=100, ge=1, le=200, description="Количество записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    current_user: User = Depends(require_employer_or_curator),
    event_service: EventService = Depends(get_event_service),
) -> EventRegistrationListResponse:
    """
    Получить список участников мероприятия.
    """
    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    return await event_service.get_participants(
        opportunity_id=opp_uuid,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{opportunity_id}/check-in",
    response_model=EventCheckInResponse,
    status_code=status.HTTP_200_OK,
    summary="Отметка присутствия участника",
    description=(
        "Отметка присутствия участника мероприятия по уникальному коду.\n\n"
        "**Требуемая роль:** EMPLOYER или CURATOR\n\n"
        "**Параметры:**\n"
        "- `check_in_code` — уникальный код участника (8 символов)\n\n"
        "**Логика:**\n"
        "- Проверяет код и отмечает `checked_in_at` текущим временем\n"
        "- Код чувствителен к регистру (приводится к upper case)\n\n"
        "**Проверки:**\n"
        "- Opportunity должно иметь тип EVENT\n"
        "- Регистрация должна существовать\n"
        "- Статус регистрации: confirmed или waitlist"
    ),
)
async def check_in_participant(
    opportunity_id: str,
    data: EventCheckInRequest,
    current_user: User = Depends(require_employer_or_curator),
    event_service: EventService = Depends(get_event_service),
) -> EventCheckInResponse:
    """
    Отметить участника как присутствующего.
    """
    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    return await event_service.check_in_participant(
        opportunity_id=opp_uuid,
        check_in_code=data.check_in_code,
        checker_user=current_user,
    )
