"""
Эндпоинты возможностей — публичный доступ (гостевой режим) и CRUD для работодателей.

Публичные эндпоинты (гостевой режим):
  - GET /api/v1/opportunities         → список карточек
  - GET /api/v1/opportunities/map     → маркеры для карты
  - GET /api/v1/opportunities/filters → фильтры для поиска
  - GET /api/v1/opportunities/{id}    → детальная информация

CRUD для работодателей (требуется авторизация + роль EMPLOYER):
  - POST   /api/v1/opportunities            → создание вакансии
  - GET    /api/v1/opportunities/me         → список своих вакансий
  - GET    /api/v1/opportunities/{id}       → детальная информация (для редактирования)
  - PATCH  /api/v1/opportunities/{id}       → редактирование
  - DELETE /api/v1/opportunities/{id}       → удаление/архивирование
  - POST   /api/v1/opportunities/{id}/publish → публикация черновика

Город определяется автоматически по IP пользователя если не передан явно.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import RoleChecker, get_db
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.opportunity import OpportunityRepository, _extract_client_ip
from src.schemas.opportunity import (
    OpportunityCreate,
    OpportunityDetail,
    OpportunityEmployerDetail,
    OpportunityEmployerListResponse,
    OpportunityFiltersResponse,
    OpportunityListResponse,
    OpportunityMapResponse,
    OpportunityPublishRequest,
    OpportunityPublishResponse,
    OpportunityUpdate,
)
from src.services.ip_geo import IPGeolocationService
from src.services.opportunity import OpportunityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


# ─── Dependency injection ─────────────────────────────────────


async def get_opportunity_service(db: AsyncSession = Depends(get_db)) -> OpportunityService:
    return OpportunityService(OpportunityRepository(db))


async def get_ip_geo_service() -> IPGeolocationService:
    """Инжектируем Redis из token_blacklist — он уже подключён в lifespan."""
    from src.utils.cache import token_blacklist

    return IPGeolocationService(redis=token_blacklist._redis)


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Опциональная авторизация для публичных эндпоинтов.

    Не выбрасывает 401 если токен отсутствует — просто возвращает None.
    Используется для is_favorited / is_applied в детальной карточке.
    """
    # Для гостей — всегда None
    # TODO: если нужен is_favorited — реализовать полноценную опциональную авторизацию
    return None


# ─── RBAC: Проверка роли EMPLOYER ─────────────────────────────

require_employer = RoleChecker([UserRole.EMPLOYER, UserRole.CURATOR])


async def _get_user_company_id(user: User, opportunity_service: OpportunityService) -> UUID:
    """
    Получить ID компании текущего пользователя.
    """
    company_id = await opportunity_service.opportunity_repo.get_company_id_by_user(user.id)
    if not company_id:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(detail="Company not found. Please create your company profile first.")
    return company_id


async def _resolve_city(
    request: Request,
    city: str | None,
    ip_geo_service: IPGeolocationService,
) -> tuple[str | None, str | None, bool]:
    """
    Определяет город для запроса.

    Returns:
        (city_for_filter, detected_city, detected_from_ip)
        - city_for_filter: город для SQL-фильтра (может быть None если не определился)
        - detected_city: город для ответа клиенту
        - detected_from_ip: True если из IP
    """
    if city:
        return city, city, False

    client_ip = _extract_client_ip(request)
    resolved_city, from_ip = await ip_geo_service.get_city_by_ip(
        client_ip,
        default_city="Москва",
    )
    return resolved_city, resolved_city, from_ip


@router.get(
    "/filters",
    response_model=OpportunityFiltersResponse,
    status_code=status.HTTP_200_OK,
    summary="Фильтры для поиска",
    description=(
        "Возвращает доступные значения для фильтрации вакансий и мероприятий:\n\n"
        "- **cities** — города с количеством предложений\n"
        "- **types** — типы (вакансия, стажировка, мероприятие, менторство)\n"
        "- **work_formats** — форматы работы (офис, гибрид, удалённо, онлайн)\n"
        "- **experience_levels** — уровни опыта (intern, junior, middle, senior, lead)\n"
        "- **employment_types** — типы занятости (полная, частичная, проектная, волонтёрство)\n"
        "- **salary_ranges** — зарплатные диапазоны\n\n"
        "Если город не передан в параметре `city`, определяется автоматически по IP пользователя."
    ),
)
async def get_filters(
    request: Request,
    city: str | None = Query(None, description="Город для фильтрации (опционально)"),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
    ip_geo_service: IPGeolocationService = Depends(get_ip_geo_service),
) -> OpportunityFiltersResponse:
    city_for_filter, detected_city, detected_from_ip = await _resolve_city(request, city, ip_geo_service)
    return await opportunity_service.get_filters(
        city=city_for_filter,
        detected_city=detected_city,
    )


@router.get(
    "/map",
    response_model=OpportunityMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Вакансии на карте",
    description=(
        "Возвращает маркеры для отображения вакансий и мероприятий на карте. "
        "Каждый маркер содержит координаты, название, компанию и зарплату.\n\n"
        "**Фильтрация:**\n"
        "- `city` — город (автоматически определяется по IP если не передан)\n"
        "- `type` — типы возможностей (vacancy, internship, event, mentoring)\n"
        "- `work_format` — формат работы (office, hybrid, remote, online)\n"
        "- `experience_level` — уровень опыта (intern, junior, middle, senior, lead)\n"
        "- `employment_type` — тип занятости (full_time, part_time, project, volunteer)\n"
        "- `salary_min`, `salary_max` — диапазон зарплаты\n"
        "- `sw_lat, sw_lng, ne_lat, ne_lng` — границы видимой области карты (bounding box)\n\n"
        "**Bouncing Box (границы карты):**\n"
        "- `sw_lat`, `sw_lng` — юго-западный угол (South-West latitude/longitude)\n"
        "- `ne_lat`, `ne_lng` — северо-восточный угол (North-East latitude/longitude)\n"
        "- Передаются при перемещении/зумировании карты для загрузки маркеров в видимой области\n\n"
        "Используйте полученные координаты (`lat`, `lng`) для отображения маркеров на карте. "
        "Кластеризацию маркеров рекомендуется выполнять на стороне клиента.\n\n"
        "📖 **Глоссарий терминов:** `GET /api/v1/glossary`"
    ),
)
async def get_map_markers(
    request: Request,
    city: str | None = Query(None, description="Город (если не передан — определяется по IP)"),
    type: str | None = Query(None, description="Типы через запятую: vacancy,internship,event,mentoring"),
    work_format: str | None = Query(None, description="office,hybrid,remote,online"),
    experience_level: str | None = Query(None, description="intern,junior,middle,senior,lead"),
    employment_type: str | None = Query(None, description="full_time,part_time,project,volunteer"),
    salary_min: int | None = Query(None, ge=0, description="Минимальная зарплата"),
    salary_max: int | None = Query(None, ge=0, description="Максимальная зарплата"),
    # Bounding box — передаётся когда пользователь двигает карту
    sw_lat: float | None = Query(None, description="Южная широта (bounding box)"),
    sw_lng: float | None = Query(None, description="Западная долгота (bounding box)"),
    ne_lat: float | None = Query(None, description="Северная широта (bounding box)"),
    ne_lng: float | None = Query(None, description="Восточная долгота (bounding box)"),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
    ip_geo_service: IPGeolocationService = Depends(get_ip_geo_service),
) -> OpportunityMapResponse:
    city_for_filter, detected_city, detected_from_ip = await _resolve_city(request, city, ip_geo_service)

    # Если bounding box передан — город не фильтруем отдельно (bounds уже ограничивают)
    filter_city = None if all(v is not None for v in [sw_lat, sw_lng, ne_lat, ne_lng]) else city_for_filter

    return await opportunity_service.get_map_markers(
        city=filter_city,
        types_str=type,
        work_format=work_format,
        experience_level=experience_level,
        employment_type=employment_type,
        salary_min=salary_min,
        salary_max=salary_max,
        sw_lat=sw_lat,
        sw_lng=sw_lng,
        ne_lat=ne_lat,
        ne_lng=ne_lng,
        detected_city=detected_city,
        detected_from_ip=detected_from_ip,
    )


@router.get(
    "",
    response_model=OpportunityListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список вакансий",
    description=(
        "Возвращает список вакансий, стажировок и мероприятий для отображения на главной странице.\n\n"
        "**Параметры:**\n"
        "- `city` — город (автоматически определяется по IP если не передан)\n"
        "- `type` — типы возможностей через запятую (vacancy, internship, event, mentoring)\n"
        "- `work_format` — формат работы (office, hybrid, remote, online)\n"
        "- `experience_level` — уровень опыта (intern, junior, middle, senior, lead)\n"
        "- `employment_type` — тип занятости (full_time, part_time, project, volunteer)\n"
        "- `salary_min`, `salary_max` — диапазон зарплаты\n"
        "- `limit`, `offset` — пагинация (по умолчанию 50, максимум 200)\n\n"
        "**Бесконечный скроллинг:**\n"
        "- Увеличивайте `offset` на `limit` после каждой загрузки\n"
        "- Продолжайте пока `offset < total` из ответа\n"
        "- Пример: offset=0 → 50 → 100 → 150...\n\n"
        "Результат отсортирован по дате публикации (новые первыми). "
        "Ответ содержит общее количество записей `total` для пагинации.\n\n"
        "📖 **Глоссарий терминов:** `GET /api/v1/glossary`"
    ),
)
async def get_opportunities(
    request: Request,
    city: str | None = Query(None, description="Город (если не передан — определяется по IP)"),
    type: str | None = Query(
        default="vacancy,internship,event",
        description="Типы через запятую: vacancy,internship,event,mentoring",
    ),
    work_format: str | None = Query(None, description="office,hybrid,remote,online"),
    experience_level: str | None = Query(None, description="intern,junior,middle,senior,lead"),
    employment_type: str | None = Query(None),
    salary_min: int | None = Query(None, ge=0),
    salary_max: int | None = Query(None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
    ip_geo_service: IPGeolocationService = Depends(get_ip_geo_service),
) -> OpportunityListResponse:
    city_for_filter, detected_city, detected_from_ip = await _resolve_city(request, city, ip_geo_service)

    return await opportunity_service.get_list(
        city=city_for_filter,
        types_str=type,
        work_format=work_format,
        experience_level=experience_level,
        employment_type=employment_type,
        salary_min=salary_min,
        salary_max=salary_max,
        limit=limit,
        offset=offset,
        detected_city=detected_city,
        detected_from_ip=detected_from_ip,
    )


@router.get(
    "/{opportunity_id}",
    response_model=OpportunityDetail,
    status_code=status.HTTP_200_OK,
    summary="Детали вакансии",
    description=(
        "Возвращает полную информацию о вакансии, стажировке или мероприятии:\n\n"
        "- Основная информация (название, описание, требования, обязанности)\n"
        "- Компания (название, логотип, город)\n"
        "- Условия (зарплата, формат работы, уровень опыта, тип занятости)\n"
        "- Контакты (имя, email, телефон, сайт)\n"
        "- Навыки и теги\n"
        "- Даты публикации и окончания\n"
        "- Счётчики (просмотры, отклики, изббранное)\n\n"
        "Для авторизованных пользователей возвращает статусы `is_favorited` и `is_applied`."
    ),
)
async def get_opportunity_detail(
    opportunity_id: str,
    current_user: User | None = Depends(get_current_user_optional),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> OpportunityDetail:
    return await opportunity_service.get_detail(opportunity_id, current_user)


@router.post(
    "",
    response_model=OpportunityEmployerDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создание вакансии",
    description=(
        "Создание новой вакансии или мероприятия от имени работодателя.\n\n"
        "**Требуемая роль:** EMPLOYER\n\n"
        "**Обязательные поля:**\n"
        "- `type` — тип: vacancy, internship, mentoring, event\n"
        "- `title` — заголовок (1-200 символов)\n"
        "- `work_format` — формат работы: office, hybrid, remote, online\n\n"
        "**Опциональные поля:**\n"
        "- Описание, требования, обязанности\n"
        "- Зарплатная вилка (min, max, currency)\n"
        "- Геолокация (город, адрес, координаты)\n"
        "- Контакты для связи\n"
        "- Навыки и теги (списки UUID)\n"
        "- Даты (публикации, окончания, для мероприятий)\n\n"
        "Вакансия создаётся в статусе **DRAFT**. Для публикации используйте `POST /opportunities/{id}/publish`."
    ),
)
async def create_opportunity(
    data: OpportunityCreate,
    current_user: User = Depends(require_employer),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> OpportunityEmployerDetail:
    """
    Создание вакансии/мероприятия.
    """
    company_id = await _get_user_company_id(current_user, opportunity_service)

    return await opportunity_service.create_opportunity(
        company_id=company_id,
        data=data,
    )


@router.get(
    "/me",
    response_model=OpportunityEmployerListResponse,
    status_code=status.HTTP_200_OK,
    summary="Список своих вакансий",
    description=(
        "Получение списка всех вакансий/мероприятий текущего работодателя с расширенной статистикой.\n\n"
        "**Требуемая роль:** EMPLOYER\n\n"
        "Возвращает все вакансии независимо от статуса:\n"
        "- DRAFT — черновики\n"
        "- ACTIVE — активные\n"
        "- PAUSED — приостановленные\n"
        "- CLOSED — закрытые/архивные\n"
        "- PLANNED — на модерации\n\n"
        "**Статистика включает:**\n"
        "- Количество просмотров\n"
        "- Количество откликов\n"
        "- Количество добавлений в избранное"
    ),
)
async def get_my_opportunities(
    limit: int = Query(default=50, ge=1, le=200, description="Количество записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    current_user: User = Depends(require_employer),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> OpportunityEmployerListResponse:
    """
    Список своих вакансий с расширенной статистикой.
    """
    company_id = await _get_user_company_id(current_user, opportunity_service)

    return await opportunity_service.get_employer_opportunities(
        company_id=company_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{opportunity_id}",
    response_model=OpportunityEmployerDetail,
    status_code=status.HTTP_200_OK,
    summary="Детали вакансии (для редактирования)",
    description=(
        "Получение полной информации о вакансии для редактирования.\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "Возвращает все поля вакансии включая:\n"
        "- ID навыков и тегов\n"
        "- Координаты (lat, lng)\n"
        "- Расширенную статистику\n"
        "- Комментарий модератора (если есть)\n\n"
        "**Важно:** Доступно только для владельца вакансии."
    ),
)
async def get_employer_opportunity_detail(
    opportunity_id: str,
    current_user: User = Depends(require_employer),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> OpportunityEmployerDetail:
    """
    Детальная информация для редактирования.
    """
    company_id = await _get_user_company_id(current_user, opportunity_service)

    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import OpportunityNotFoundError

        raise OpportunityNotFoundError() from e

    return await opportunity_service.get_employer_detail(
        opportunity_id=opp_uuid,
        company_id=company_id,
    )


@router.patch(
    "/{opportunity_id}",
    response_model=OpportunityEmployerDetail,
    status_code=status.HTTP_200_OK,
    summary="Редактирование вакансии",
    description=(
        "Обновление существующей вакансии/мероприятия.\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "**Можно обновлять:**\n"
        "- Основную информацию (title, description, requirements, responsibilities)\n"
        "- Формат работы, уровень опыта, тип занятости\n"
        "- Зарплатные параметры\n"
        "- Геолокацию (город, адрес, координаты)\n"
        "- Контакты\n"
        "- Навыки и теги (полная замена списков)\n"
        "- Даты\n\n"
        "**Нельзя изменить через PATCH:**\n"
        "- `type` — тип возможности (только при создании)\n"
        "- Статус (используйте `POST /opportunities/{id}/publish`)\n\n"
        "**Важно:** Доступно только для владельца вакансии."
    ),
)
async def update_opportunity(
    opportunity_id: str,
    data: OpportunityUpdate,
    current_user: User = Depends(require_employer),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> OpportunityEmployerDetail:
    """
    Редактирование вакансии.
    """
    company_id = await _get_user_company_id(current_user, opportunity_service)

    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import OpportunityNotFoundError

        raise OpportunityNotFoundError() from e

    return await opportunity_service.update_opportunity(
        opportunity_id=opp_uuid,
        company_id=company_id,
        data=data,
    )


@router.delete(
    "/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление вакансии",
    description=(
        "Мягкое удаление вакансии/мероприятия (перевод в статус CLOSED).\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "Вакансия не удаляется физически из БД, а помечается как закрытая.\n"
        "Закрытые вакансии не отображаются в публичном каталоге.\n\n"
        "**Важно:** Доступно только для владельца вакансии."
    ),
)
async def delete_opportunity(
    opportunity_id: str,
    current_user: User = Depends(require_employer),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> None:
    """
    Удаление/архивирование вакансии.
    """
    company_id = await _get_user_company_id(current_user, opportunity_service)

    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import OpportunityNotFoundError

        raise OpportunityNotFoundError() from e

    await opportunity_service.delete_opportunity(
        opportunity_id=opp_uuid,
        company_id=company_id,
    )


@router.post(
    "/{opportunity_id}/publish",
    response_model=OpportunityPublishResponse,
    status_code=status.HTTP_200_OK,
    summary="Публикация черновика",
    description=(
        "Публикация вакансии (перевод из DRAFT в ACTIVE).\n\n"
        "**Требуемая роль:** EMPLOYER + владелец вакансии\n\n"
        "**Логика модерации:**\n"
        "- Если `requires_moderation=true` (по умолчанию) → статус PLANNED, ожидание куратора\n"
        "- Если `requires_moderation=false` → статус ACTIVE сразу (если есть права)\n\n"
        "**Проверки перед публикацией:**\n"
        "- Заполнены обязательные поля (title, description, work_format)\n"
        "- Вакансия в статусе DRAFT\n\n"
        "**Важно:** Доступно только для владельца вакансии."
    ),
)
async def publish_opportunity(
    opportunity_id: str,
    data: OpportunityPublishRequest | None = None,
    current_user: User = Depends(require_employer),
    opportunity_service: OpportunityService = Depends(get_opportunity_service),
) -> OpportunityPublishResponse:
    """
    Публикация черновика.
    """
    company_id = await _get_user_company_id(current_user, opportunity_service)

    try:
        opp_uuid = UUID(opportunity_id)
    except ValueError as e:
        from src.core.exceptions import OpportunityNotFoundError

        raise OpportunityNotFoundError() from e

    # По умолчанию требуется модерация
    requires_moderation = True
    if data and hasattr(data, "curator_comment") and data.curator_comment:
        # Если есть комментарий — сохраняем (можно добавить в сервис)
        logger.info("Curator comment provided for opportunity %s: %s", opp_uuid, data.curator_comment)

    return await opportunity_service.publish_opportunity(
        opportunity_id=opp_uuid,
        company_id=company_id,
        requires_moderation=requires_moderation,
    )
