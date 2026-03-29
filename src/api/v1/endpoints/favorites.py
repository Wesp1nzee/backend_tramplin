"""
Эндпоинты для работы с избранным (вакансии и компании).

Публичные эндпоинты (гостевой режим):
  - Неавторизованные пользователи хранят избранное в localStorage браузера
  - При авторизации фронт отправляет список ID для синхронизации с БД

Авторизованные пользователи (APPLICANT):
  - POST   /api/v1/favorites/sync                → синхронизация localStorage с БД
  - GET    /api/v1/favorites/opportunities       → список избранных вакансий
  - GET    /api/v1/favorites/companies           → список избранных компаний
  - POST   /api/v1/favorites/opportunities/{id}  → добавить вакансию в избранное
  - DELETE /api/v1/favorites/opportunities/{id}  → удалить вакансию из избранного
  - POST   /api/v1/favorites/companies/{id}      → добавить компанию в избранное
  - DELETE /api/v1/favorites/companies/{id}      → удалить компанию из избранного
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import RoleChecker, get_db
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.favorites import FavoriteCompanyRepository, FavoriteRepository
from src.repositories.opportunity import OpportunityRepository
from src.schemas.favorites import (
    FavoriteCompanyItem,
    FavoriteCompanyListResponse,
    FavoriteOpportunityCreate,
    FavoriteOpportunityItem,
    FavoriteOpportunityListResponse,
    FavoriteSyncRequest,
    FavoriteSyncResponse,
)
from src.services.favorites import FavoriteCompanyService, FavoriteService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/favorites", tags=["Favorites"])


# ─── Dependency injection ─────────────────────────────────────


async def get_favorite_service(db: AsyncSession = Depends(get_db)) -> FavoriteService:
    return FavoriteService(
        favorite_repo=FavoriteRepository(db),
        opportunity_repo=OpportunityRepository(db),
        favorite_company_repo=FavoriteCompanyRepository(db),
    )


async def get_favorite_company_service(db: AsyncSession = Depends(get_db)) -> FavoriteCompanyService:
    return FavoriteCompanyService(
        favorite_company_repo=FavoriteCompanyRepository(db),
    )


# ─── RBAC: Проверка роли APPLICANT ─────────────────────────────

require_applicant = RoleChecker([UserRole.APPLICANT])


# ─── Синхронизация ────────────────────────────────────────────


@router.post(
    "/sync",
    response_model=FavoriteSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Синхронизация избранного",
    description=(
        "Синхронизация избранного из localStorage при логине/регистрации.\n\n"
        "**Логика работы:**\n"
        "- Фронтенд отправляет ID вакансий и компаний из localStorage\n"
        "- Бэкенд объединяет с существующими записями в БД (без дубликатов)\n"
        "- Возвращает итоговый список синхронизированных ID\n\n"
        "**Идемпотентность:**\n"
        "- Эндпоинт можно вызывать многократно без побочных эффектов\n"
        "- Дубликаты автоматически отфильтровываются\n\n"
        "**Требуемая роль:** APPLICANT"
    ),
)
async def sync_favorites(
    data: FavoriteSyncRequest,
    current_user: User = Depends(require_applicant),
    favorite_service: FavoriteService = Depends(get_favorite_service),
) -> FavoriteSyncResponse:
    """
    Синхронизировать избранное из localStorage.
    """
    return await favorite_service.sync_favorites(
        user=current_user,
        data=data,
    )


# ─── Избранные вакансии ───────────────────────────────────────


@router.get(
    "/opportunities",
    response_model=FavoriteOpportunityListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список избранных вакансий",
    description=(
        "Получение списка избранных вакансий текущего пользователя.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "Возвращает все вакансии, добавленные в избранное, с информацией:\n"
        "- Основная информация о вакансии\n"
        "- Компания (название, логотип, город)\n"
        "- Пользовательская заметка (если есть)\n"
        "- Дата добавления\n\n"
        "Результат отсортирован по дате добавления (новые первыми)."
    ),
)
async def get_favorite_opportunities(
    current_user: User = Depends(require_applicant),
    favorite_service: FavoriteService = Depends(get_favorite_service),
) -> FavoriteOpportunityListResponse:
    """
    Получить список избранных вакансий.
    """
    return await favorite_service.get_user_favorites(user_id=current_user.id)


@router.post(
    "/opportunities/{opportunity_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Добавить вакансию в избранное",
    description=(
        "Добавление вакансии в избранное.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "**Опционально:**\n"
        "- `note` — пользовательская заметка к вакансии (до 1000 символов)\n\n"
        "**Проверки:**\n"
        "- Вакансия должна существовать и быть активной (ACTIVE)\n"
        "- Нельзя добавить вакансию своей собственной компании\n"
        "- Повторное добавление игнорируется (идемпотентность)"
    ),
)
async def add_to_favorites(
    opportunity_id: str,
    data: FavoriteOpportunityCreate | None = None,
    current_user: User = Depends(require_applicant),
    favorite_service: FavoriteService = Depends(get_favorite_service),
) -> FavoriteOpportunityItem:
    """
    Добавить вакансию в избранное.
    """
    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    note = data.note if data else None

    return await favorite_service.add_to_favorites(
        user=current_user,
        opportunity_id=opp_uuid,
        note=note,
    )


@router.delete(
    "/opportunities/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить вакансию из избранного",
    description=(
        "Удаление вакансии из избранного.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "Если вакансия не была добавлена в избранное, запрос игнорируется."
    ),
)
async def remove_from_favorites(
    opportunity_id: str,
    current_user: User = Depends(require_applicant),
    favorite_service: FavoriteService = Depends(get_favorite_service),
) -> None:
    """
    Удалить вакансию из избранного.
    """
    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    await favorite_service.remove_from_favorites(
        user_id=current_user.id,
        opportunity_id=opp_uuid,
    )


# ─── Избранные компании ───────────────────────────────────────


@router.get(
    "/companies",
    response_model=FavoriteCompanyListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список избранных компаний",
    description=(
        "Получение списка избранных компаний текущего пользователя.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "Возвращает все компании, добавленные в избранное, с информацией:\n"
        "- Название компании\n"
        "- Логотип\n"
        "- Город\n"
        "- Дата добавления\n\n"
        "Результат отсортирован по дате добавления (новые первыми)."
    ),
)
async def get_favorite_companies(
    current_user: User = Depends(require_applicant),
    favorite_company_service: FavoriteCompanyService = Depends(get_favorite_company_service),
) -> FavoriteCompanyListResponse:
    """
    Получить список избранных компаний.
    """
    return await favorite_company_service.get_user_favorite_companies(user_id=current_user.id)


@router.post(
    "/companies/{company_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Добавить компанию в избранное",
    description=(
        "Добавление компании в избранное.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "**Проверки:**\n"
        "- Компания должна существовать и быть активной\n"
        "- Нельзя добавить свою собственную компанию\n"
        "- Повторное добавление игнорируется (идемпотентность)"
    ),
)
async def add_company_to_favorites(
    company_id: str,
    current_user: User = Depends(require_applicant),
    favorite_company_service: FavoriteCompanyService = Depends(get_favorite_company_service),
) -> FavoriteCompanyItem:
    """
    Добавить компанию в избранное.
    """
    try:
        company_uuid = UUID(company_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    return await favorite_company_service.add_company_to_favorites(
        user=current_user,
        company_id=company_uuid,
    )


@router.delete(
    "/companies/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить компанию из избранного",
    description=(
        "Удаление компании из избранного.\n\n"
        "**Требуемая роль:** APPLICANT\n\n"
        "Если компания не была добавлена в избранное, запрос игнорируется."
    ),
)
async def remove_company_from_favorites(
    company_id: str,
    current_user: User = Depends(require_applicant),
    favorite_company_service: FavoriteCompanyService = Depends(get_favorite_company_service),
) -> None:
    """
    Удалить компанию из избранного.
    """
    try:
        company_uuid = UUID(company_id)
    except ValueError as e:
        from src.core.exceptions import NotFoundError

        raise NotFoundError() from e

    await favorite_company_service.remove_company_from_favorites(
        user_id=current_user.id,
        company_id=company_uuid,
    )
