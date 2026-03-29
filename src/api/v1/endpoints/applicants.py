"""
Эндпоинты для поиска соискателей работодателями.

Для работодателей и кураторов (EMPLOYER, CURATOR):
  - GET /api/v1/applicants/search          → поиск соискателей
  - GET /api/v1/applicants/{profile_id}    → детальный профиль соискателя
  - POST /api/v1/applicants/{profile_id}/contact → запрос на установление контакта
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import RoleChecker, get_db
from src.models.enums import ContactStatus, NotificationType, UserRole
from src.models.user import User
from src.repositories.applicant import ApplicantRepository
from src.schemas.user import (
    ApplicantDetailResponse,
    ApplicantSearchResponse,
)
from src.services.applicant import ApplicantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applicants", tags=["Applicants"])


# ─── Dependency injection ─────────────────────────────────────


async def get_applicant_service(db: AsyncSession = Depends(get_db)) -> ApplicantService:
    return ApplicantService(
        applicant_repo=ApplicantRepository(db),
    )


# ─── RBAC: Проверка ролей ─────────────────────────────────────

require_employer_or_curator = RoleChecker([UserRole.EMPLOYER, UserRole.CURATOR])


# ─── Search endpoints ─────────────────────────────────────────


@router.get(
    "/search",
    response_model=ApplicantSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Поиск соискателей",
    description=(
        "Поиск соискателей по навыкам, университету, году выпуска.\n\n"
        "**Требуемая роль:** EMPLOYER или CURATOR\n\n"
        "**Параметры поиска:**\n"
        "- `skills` — список навыков через запятую (Python, FastAPI, PostgreSQL)\n"
        "- `university` — часть названия университета (частичное совпадение)\n"
        "- `graduation_year` — год выпуска\n"
        "- `city` — город (поиск по университету)\n"
        "- `limit`, `offset` — пагинация\n\n"
        "**Приватность:**\n"
        "- В поиске участвуют только профили с `public_profile=true`\n"
        "- Скрытые профили не отображаются в результатах\n\n"
        "**Сортировка:**\n"
        "- При поиске по навыкам — по релевантности (количеству совпадений)\n"
        "- Без навыков — по году выпуска (recent first)\n\n"
        "**Поле `is_contact`:**\n"
        "- `true` если у работодателя уже установлен контакт с соискателем"
    ),
)
async def search_applicants(
    skills: str | None = Query(None, description="Навыки через запятую: Python,FastAPI,PostgreSQL"),
    university: str | None = Query(None, description="Часть названия университета"),
    graduation_year: int | None = Query(None, ge=1990, le=2100, description="Год выпуска"),
    city: str | None = Query(None, description="Город"),
    limit: int = Query(default=50, ge=1, le=100, description="Количество записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    current_user: User = Depends(require_employer_or_curator),
    applicant_service: ApplicantService = Depends(get_applicant_service),
) -> ApplicantSearchResponse:
    """
    Поиск соискателей с фильтрами.
    """
    # Парсим навыки из строки
    skills_list = None
    if skills:
        skills_list = [s.strip() for s in skills.split(",") if s.strip()]

    return await applicant_service.search_applicants(
        skills=skills_list,
        university=university,
        graduation_year=graduation_year,
        city=city,
        limit=limit,
        offset=offset,
        requester_user=current_user,
    )


@router.get(
    "/{profile_id}",
    response_model=ApplicantDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Профиль соискателя",
    description=(
        "Получение детального профиля соискателя.\n\n"
        "**Требуемая роль:** EMPLOYER или CURATOR\n\n"
        "**Приватность:**\n"
        "- Если `public_profile=false`: большинство полей скрыты (показывается 'Скрыто')\n"
        "- Если `show_contacts=false`: контакты скрыты (телефон, соцсети, CV)\n"
        "- Кураторы видят все данные независимо от настроек приватности\n"
        "- Контакты видны только если установлен контакт (статус ACCEPTED)\n\n"
        "**Поле `is_contact`:**\n"
        "- `true` если у работодателя уже установлен контакт с соискателем"
    ),
)
async def get_applicant_profile(
    profile_id: str,
    current_user: User = Depends(require_employer_or_curator),
    applicant_service: ApplicantService = Depends(get_applicant_service),
) -> ApplicantDetailResponse:
    """
    Получить детальный профиль соискателя.
    """
    try:
        profile_uuid = UUID(profile_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    return await applicant_service.get_applicant_detail(
        profile_id=profile_uuid,
        requester_user=current_user,
    )


@router.post(
    "/{profile_id}/contact",
    status_code=status.HTTP_201_CREATED,
    summary="Запрос на установление контакта",
    description=(
        "Отправка запроса на установление профессионального контакта.\n\n"
        "**Требуемая роль:** EMPLOYER\n\n"
        "**Параметры:**\n"
        "- `message` — опциональное сообщение к запросу (до 500 символов)\n\n"
        "**Логика:**\n"
        "- Создаётся запись в Contact со статусом PENDING\n"
        "- Соискатель получает уведомление (NotificationType.CONTACT_REQUEST)\n"
        "- При уже существующем контакте возвращается ошибка 409\n\n"
        "**Проверки:**\n"
        "- Нельзя отправить запрос самому себе\n"
        "- Нельзя отправить повторный запрос при существующем PENDING"
    ),
)
async def send_contact_request(
    profile_id: str,
    message: str | None = Query(None, max_length=500, description="Сообщение к запросу"),
    current_user: User = Depends(require_employer_or_curator),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Отправить запрос на установление контакта.
    """
    from sqlalchemy import select

    from src.core.exceptions import NotFoundError
    from src.models.social import Contact
    from src.models.user import Profile

    try:
        profile_uuid = UUID(profile_id)
    except ValueError as e:
        raise NotFoundError() from e

    # Проверяем существование профиля
    profile_result = await db.execute(select(Profile).where(Profile.id == profile_uuid))
    profile = profile_result.scalar_one_or_none()

    if not profile:
        raise NotFoundError(detail="Profile not found")

    # Нельзя отправить запрос самому себе
    if profile.user_id == current_user.id:
        from src.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError(detail="Cannot send contact request to yourself")

    # Проверяем существующий контакт
    existing_result = await db.execute(
        select(Contact).where(
            ((Contact.requester_id == current_user.id) & (Contact.addressee_id == profile.user_id))
            | ((Contact.requester_id == profile.user_id) & (Contact.addressee_id == current_user.id))
        )
    )
    existing_contact = existing_result.scalar_one_or_none()

    if existing_contact:
        from src.core.exceptions import ContactRequestAlreadyExistsError

        raise ContactRequestAlreadyExistsError()

    # Создаём новый контакт
    contact = Contact(
        requester_id=current_user.id,
        addressee_id=profile.user_id,
        status=ContactStatus.PENDING,
        message=message,
    )
    db.add(contact)

    # Создаём уведомление
    from src.models.notification import Notification

    notification = Notification(
        recipient_id=profile.user_id,
        type=NotificationType.CONTACT_REQUEST,
        title="Новый запрос в контакты",
        body=f"{current_user.profile.first_name} {current_user.profile.last_name} хочет добавить вас в контакты",
        payload={
            "type": "contact_request",
            "requester_id": str(current_user.id),
            "contact_id": str(contact.id),
        },
    )
    db.add(notification)

    await db.commit()

    return {
        "id": str(contact.id),
        "status": ContactStatus.PENDING,
        "message": "Contact request sent successfully",
    }
