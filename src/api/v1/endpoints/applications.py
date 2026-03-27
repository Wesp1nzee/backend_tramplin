"""
Эндпоинты откликов (Applications).

Для соискателя (APPLICANT):
  - POST   /applications            → Создать отклик
  - GET    /applications/me         → Список моих откликов
  - GET    /applications/me/{id}    → Детали моего отклика
  - DELETE /applications/me/{id}    → Отозвать отклик

Для работодателя (EMPLOYER):
  - GET    /opportunities/{id}/applications → Список откликов на мою вакансию
  - GET    /applications/{id}               → Детали отклика
  - PATCH  /applications/{id}/status        → Смена статуса
  - PATCH  /applications/{id}/feedback      → Обратная связь
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import RoleChecker, get_db
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.application import ApplicationRepository
from src.schemas.application import (
    ApplicationApplicantDetail,
    ApplicationCreate,
    ApplicationEmployerDetail,
    ApplicationEmployerListResponse,
    ApplicationFeedbackUpdate,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusUpdate,
)
from src.services.application import ApplicationService

logger = logging.getLogger(__name__)

# ─── Роутеры ─────────────────────────────────────────────────
# Разделяем по префиксам, чтобы маршруты регистрировались корректно

# Для соискателя: все пути начинаются с /applications
applicant_router = APIRouter(prefix="/applications", tags=["Applications"])

# Для работодателя: список откликов на вакансию (путь через opportunity)
employer_opportunities_router = APIRouter(prefix="/opportunities", tags=["Applications"])

# Для работодателя: управление конкретным откликом (путь через application)
employer_applications_router = APIRouter(prefix="/applications", tags=["Applications"])


# ─── Dependency injection ─────────────────────────────────────


async def get_application_service(
    db: AsyncSession = Depends(get_db),
) -> ApplicationService:
    return ApplicationService(ApplicationRepository(db))


# ─── RBAC: Проверка ролей ─────────────────────────────────────

require_applicant = RoleChecker([UserRole.APPLICANT, UserRole.CURATOR])
require_employer = RoleChecker([UserRole.EMPLOYER, UserRole.CURATOR])


async def _get_user_profile_id(user: User) -> UUID:
    """
    Получить ID профиля текущего пользователя.
    """
    if not user.profile:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(detail="User profile not found")
    return user.profile.id


async def _get_user_company_id(user: User, application_service: ApplicationService) -> UUID:
    """
    Получить ID компании текущего работодателя.
    """
    company_id = await application_service.application_repo.get_company_id_by_user(user.id)
    if not company_id:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(detail="Company not found. Please create your company profile first.")
    return company_id


# ════════════════════════════════════════════════════════════
#  Эндпоинты для соискателя (APPLICANT)
# ════════════════════════════════════════════════════════════


@applicant_router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание отклика",
    description=(
        "Создание отклика на вакансию/стажировку/мероприятие.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "**Проверки:**\n"
        "- Вакансия активна (status=ACTIVE)\n"
        "- Компания верифицирована (verification_status=APPROVED)\n"
        "- Нет дублирующегося отклика\n"
        "- Профиль соискателя существует\n\n"
        "**Что делает:**\n"
        "- Делает снапшот cv_url из профиля соискателя\n"
        "- Создаёт отклик со статусом PENDING\n"
        "- Инкрементирует applications_count у вакансии\n"
        "- Создаёт уведомление работодателю\n\n"
        "**Поля:**\n"
        "- `opportunity_id` — ID вакансии (обязательно)\n"
        "- `cover_letter` — сопроводительное письмо (опционально, до 5000 символов)"
    ),
)
async def create_application(
    data: ApplicationCreate,
    current_user: User = Depends(require_applicant),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationResponse:
    """
    Создать отклик на вакансию.
    """
    applicant_id = await _get_user_profile_id(current_user)

    return await application_service.create_application(
        applicant_id=applicant_id,
        data=data,
    )


@applicant_router.get(
    "/me",
    response_model=ApplicationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список моих откликов",
    description=(
        "Получение списка всех откликов текущего соискателя с пагинацией.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "Возвращает отклики в порядке создания (новые первыми).\n"
        "Каждый элемент содержит:\n"
        "- Основную информацию об отклике (статус, дата создания)\n"
        "- Краткие данные вакансии\n"
        "- Краткие данные компании\n\n"
        "**Пагинация:**\n"
        "- `limit` — количество записей (по умолчанию 50, максимум 200)\n"
        "- `offset` — смещение (по умолчанию 0)\n"
        "- `total` — общее количество записей"
    ),
)
async def get_my_applications(
    limit: int = Query(default=50, ge=1, le=200, description="Количество записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    current_user: User = Depends(require_applicant),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationListResponse:
    """
    Список моих откликов с пагинацией.
    """
    applicant_id = await _get_user_profile_id(current_user)

    return await application_service.get_applicant_applications(
        applicant_id=applicant_id,
        limit=limit,
        offset=offset,
    )


@applicant_router.get(
    "/me/{application_id}",
    response_model=ApplicationApplicantDetail,
    status_code=status.HTTP_200_OK,
    summary="Детали моего отклика",
    description=(
        "Получение полной информации об отклике соискателя.\n\n"
        "**Требуемая роль:** APPLICANT + владелец отклика\n\n"
        "Возвращает:\n"
        "- Статус отклика и историю изменений\n"
        "- Комментарий работодателя (если есть)\n"
        "- Данные вакансии и компании\n"
        "- Даты просмотра и ответа\n\n"
        "**Важно:** Доступно только для владельца отклика."
    ),
)
async def get_my_application_detail(
    application_id: str,
    current_user: User = Depends(require_applicant),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationApplicantDetail:
    """
    Детали моего отклика.
    """
    applicant_id = await _get_user_profile_id(current_user)

    try:
        app_uuid = UUID(application_id)
    except ValueError as e:
        from src.core.exceptions import ApplicationNotFoundError

        raise ApplicationNotFoundError() from e

    return await application_service.get_applicant_application_detail(
        applicant_id=applicant_id,
        application_id=app_uuid,
    )


@applicant_router.delete(
    "/me/{application_id}",
    status_code=status.HTTP_200_OK,
    summary="Отозвать отклик",
    description=(
        "Отзыв отклика соискателем.\n\n"
        "**Требуемая роль:** APPLICANT + владелец отклика\n\n"
        "**Разрешено** если статус:\n"
        "- PENDING (на рассмотрении)\n"
        "- VIEWED (просмотрен работодателем)\n\n"
        "**Запрещено** если статус:\n"
        "- ACCEPTED (одобрен)\n"
        "- REJECTED (отклонён)\n"
        "- RESERVE (в резерве)\n\n"
        "После отзыва статус меняется на WITHDRAWN.\n\n"
        "**Важно:** Доступно только для владельца отклика."
    ),
)
async def withdraw_application(
    application_id: str,
    current_user: User = Depends(require_applicant),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationApplicantDetail:
    """
    Отозвать отклик.
    """
    applicant_id = await _get_user_profile_id(current_user)

    try:
        app_uuid = UUID(application_id)
    except ValueError as e:
        from src.core.exceptions import ApplicationNotFoundError

        raise ApplicationNotFoundError() from e

    return await application_service.withdraw_application(
        applicant_id=applicant_id,
        application_id=app_uuid,
    )


# ════════════════════════════════════════════════════════════
#  Эндпоинты для работодателя (EMPLOYER)
# ════════════════════════════════════════════════════════════

# ─── Через /opportunities/{id}/applications ──────────────────


@employer_opportunities_router.get(
    "/{opportunity_id}/applications",
    response_model=ApplicationEmployerListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список откликов на вакансию",
    description=(
        "Получение списка откликов на вакансию работодателя.\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "Возвращает отклики в порядке создания (новые первыми).\n"
        "Каждый элемент содержит:\n"
        "- Данные соискателя (с учётом настроек приватности)\n"
        "- Сопроводительное письмо\n"
        "- Статус отклика\n"
        "- Даты просмотра и ответа\n\n"
        "**Пагинация:**\n"
        "- `limit` — количество записей (по умолчанию 50, максимум 200)\n"
        "- `offset` — смещение (по умолчанию 0)\n\n"
        "**Важно:** Доступно только для владельца вакансии."
    ),
)
async def get_opportunity_applications(
    opportunity_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Количество записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    current_user: User = Depends(require_employer),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationEmployerListResponse:
    """
    Список откликов на вакансию работодателя.
    """
    company_id = await _get_user_company_id(current_user, application_service)

    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import ApplicationNotFoundError

        raise ApplicationNotFoundError() from e

    return await application_service.get_opportunity_applications(
        company_id=company_id,
        opportunity_id=opp_uuid,
        limit=limit,
        offset=offset,
    )


# ─── Через /applications/{id} (управление откликом) ──────────


@employer_applications_router.get(
    "/{application_id}",
    response_model=ApplicationEmployerDetail,
    status_code=status.HTTP_200_OK,
    summary="Детали отклика",
    description=(
        "Получение полной информации об отклике для работодателя.\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "Возвращает:\n"
        "- Данные соискателя (профиль, резюме)\n"
        "- Сопроводительное письмо\n"
        "- Историю изменений статуса\n"
        "- Внутреннюю заметку работодателя\n"
        "- Данные вакансии\n\n"
        "**Важно:** Доступно только для владельца вакансии."
    ),
)
async def get_employer_application_detail(
    application_id: str,
    current_user: User = Depends(require_employer),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationEmployerDetail:
    """
    Детали отклика для работодателя.
    """
    company_id = await _get_user_company_id(current_user, application_service)

    try:
        app_uuid = UUID(application_id)
    except ValueError as e:
        from src.core.exceptions import ApplicationNotFoundError

        raise ApplicationNotFoundError() from e

    return await application_service.get_employer_application_detail(
        company_id=company_id,
        application_id=app_uuid,
    )


@employer_applications_router.patch(
    "/{application_id}/status",
    response_model=ApplicationEmployerDetail,
    status_code=status.HTTP_200_OK,
    summary="Смена статуса отклика",
    description=(
        "Обновление статуса отклика работодателем.\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "**Разрешённые переходы:**\n"
        "- PENDING → VIEWED (просмотрен)\n"
        "- PENDING → ACCEPTED (одобрен)\n"
        "- PENDING → REJECTED (отклонён)\n"
        "- PENDING → RESERVE (в резерве)\n"
        "- VIEWED → ACCEPTED\n"
        "- VIEWED → REJECTED\n"
        "- VIEWED → RESERVE\n\n"
        "**Запрещено:**\n"
        "- Менять статус отозванного отклика (WITHDRAWN)\n"
        "- Менять статус обратно на PENDING\n\n"
        "**Поля:**\n"
        "- `status` — новый статус (обязательно)\n"
        "- `employer_comment` — комментарий для соискателя (опционально)\n\n"
        "Отправляет уведомление соискателю."
    ),
)
async def update_application_status(
    application_id: str,
    data: ApplicationStatusUpdate,
    current_user: User = Depends(require_employer),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationEmployerDetail:
    """
    Смена статуса отклика.
    """
    company_id = await _get_user_company_id(current_user, application_service)

    try:
        app_uuid = UUID(application_id)
    except ValueError as e:
        from src.core.exceptions import ApplicationNotFoundError

        raise ApplicationNotFoundError() from e

    return await application_service.update_application_status(
        company_id=company_id,
        application_id=app_uuid,
        data=data,
    )


@employer_applications_router.patch(
    "/{application_id}/feedback",
    response_model=ApplicationEmployerDetail,
    status_code=status.HTTP_200_OK,
    summary="Обратная связь по отклику",
    description=(
        "Добавление обратной связи от работодателя.\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "**Поля:**\n"
        "- `employer_comment` — комментарий для соискателя (виден в ЛК кандидата)\n"
        "- `employer_note` — внутренняя заметка (не видна соискателю)\n\n"
        "Оба поля опциональны. Можно обновлять как по отдельности, так и вместе.\n\n"
        "**Важно:** Доступно только для владельца вакансии."
    ),
)
async def update_application_feedback(
    application_id: str,
    data: ApplicationFeedbackUpdate,
    current_user: User = Depends(require_employer),
    application_service: ApplicationService = Depends(get_application_service),
) -> ApplicationEmployerDetail:
    """
    Обратная связь по отклику.
    """
    company_id = await _get_user_company_id(current_user, application_service)

    try:
        app_uuid = UUID(application_id)
    except ValueError as e:
        from src.core.exceptions import ApplicationNotFoundError

        raise ApplicationNotFoundError() from e

    return await application_service.update_application_feedback(
        company_id=company_id,
        application_id=app_uuid,
        data=data,
    )
