"""
Эндпоинты возможностей — публичный доступ (гостевой режим).

Предоставляют данные для главной страницы:
  - GET /api/v1/opportunities         → список карточек
  - GET /api/v1/opportunities/map     → маркеры для карты
  - GET /api/v1/opportunities/filters → фильтры для поиска
  - GET /api/v1/opportunities/{id}    → детальная информация

Город определяется автоматически по IP пользователя если не передан явно.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import get_db
from src.models.user import User
from src.repositories.opportunity import OpportunityRepository, _extract_client_ip
from src.schemas.opportunity import (
    OpportunityDetail,
    OpportunityFiltersResponse,
    OpportunityListResponse,
    OpportunityMapResponse,
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


# ─── Хелпер: определение города ──────────────────────────────


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


# ═════════════════════════════════════════════════════════════
#  ЭНДПОИНТЫ (порядок важен!)
# ═════════════════════════════════════════════════════════════


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
