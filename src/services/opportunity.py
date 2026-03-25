"""
Бизнес-логика возможностей (вакансии, стажировки, мероприятия).

Сервис отвечает за:
  - Разбор типов из строки "vacancy,event" → список
  - Делегирование в репозиторий
  - Конвертацию ORM → DTO для детальной карточки
  - Проверку is_active/is_moderated (публичный доступ)
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import NotFoundError
from src.models.user import User
from src.repositories.opportunity import OpportunityRepository
from src.schemas.opportunity import (
    CompanyShort,
    LocationInfo,
    OpportunityDetail,
    OpportunityFiltersResponse,
    OpportunityListResponse,
    OpportunityMapResponse,
    SalaryInfo,
)

logger = logging.getLogger(__name__)


class OpportunityService:
    def __init__(self, opportunity_repo: OpportunityRepository) -> None:
        self.opportunity_repo = opportunity_repo

    async def get_list(
        self,
        *,
        city: str | None = None,
        types_str: str | None = None,
        work_format: str | None = None,
        experience_level: str | None = None,
        employment_type: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        limit: int = 50,
        offset: int = 0,
        detected_city: str | None = None,
        detected_from_ip: bool = False,
    ) -> OpportunityListResponse:
        """
        Публичный список возможностей.

        Args:
            city: Явно переданный город (переопределяет IP)
            types_str: Типы через запятую: "vacancy,event"
            detected_city: Город после IP-геолокации (для ответа)
            detected_from_ip: Флаг для ответа — был ли город из IP
        """
        types = self._parse_types(types_str)

        items, total = await self.opportunity_repo.get_public_list(
            city=city,
            types=types,
            work_format=work_format,
            experience_level=experience_level,
            employment_type=employment_type,
            salary_min=salary_min,
            salary_max=salary_max,
            limit=limit,
            offset=offset,
        )

        return OpportunityListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            detected_city=detected_city,
            detected_from_ip=detected_from_ip,
        )

    async def get_map_markers(
        self,
        *,
        city: str | None = None,
        types_str: str | None = None,
        work_format: str | None = None,
        experience_level: str | None = None,
        employment_type: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        sw_lat: float | None = None,
        sw_lng: float | None = None,
        ne_lat: float | None = None,
        ne_lng: float | None = None,
        detected_city: str | None = None,
        detected_from_ip: bool = False,
    ) -> OpportunityMapResponse:
        """Маркеры для карты. Кластеризацию делает react-leaflet-cluster."""
        types = self._parse_types(types_str)

        markers = await self.opportunity_repo.get_map_markers(
            city=city,
            types=types,
            work_format=work_format,
            experience_level=experience_level,
            employment_type=employment_type,
            salary_min=salary_min,
            salary_max=salary_max,
            sw_lat=sw_lat,
            sw_lng=sw_lng,
            ne_lat=ne_lat,
            ne_lng=ne_lng,
        )

        return OpportunityMapResponse(
            markers=markers,
            total=len(markers),
            detected_city=detected_city,
            detected_from_ip=detected_from_ip,
        )

    async def get_detail(
        self,
        opportunity_id: str,
        current_user: User | None = None,
    ) -> OpportunityDetail:
        """
        Детальная карточка возможности.

        Инкрементирует счётчик просмотров (fire-and-forget, не блокирует ответ).
        Для авторизованного пользователя возвращает is_favorited/is_applied.
        """
        try:
            opp_uuid = UUID(opportunity_id)
        except ValueError as e:
            raise NotFoundError() from e

        opp = await self.opportunity_repo.get_detail(opp_uuid)
        if not opp:
            raise NotFoundError()

        # Инкремент просмотров в фоне (не ждём)
        import asyncio

        asyncio.create_task(self.opportunity_repo.increment_views(opp_uuid))

        company = opp.company
        skills = [os.skill.name for os in opp.opportunity_skills if os.skill]
        tags = [ot.tag.name for ot in opp.opportunity_tags if ot.tag]

        # Координаты из PostGIS — если есть location
        lat, lng = None, None
        if opp.location is not None:
            try:
                from geoalchemy2.functions import ST_X, ST_Y
                from sqlalchemy import select

                lat_result = await self.opportunity_repo.db.execute(
                    select(
                        ST_Y(opp.location),
                        ST_X(opp.location),
                    )
                )
                lat, lng = lat_result.one()
            except SQLAlchemyError as e:
                logger.debug("Failed to extract coordinates for opportunity %s: %s", opp.id, e)
                lat, lng = None, None
            except (TypeError, ValueError) as e:
                logger.debug("Invalid coordinate format for opportunity %s: %s", opp.id, e)
                lat, lng = None, None

        is_favorited = False
        is_applied = False
        # TODO: запросить из БД если current_user не None
        # if current_user:
        #     is_favorited = await self._check_favorite(opp_uuid, current_user.id)
        #     is_applied = await self._check_applied(opp_uuid, current_user.id)

        return OpportunityDetail(
            id=opp.id,
            type=opp.type,
            title=opp.title,
            status=opp.status,
            description=opp.description,
            requirements=opp.requirements,
            responsibilities=opp.responsibilities,
            work_format=opp.work_format,
            employment_type=opp.employment_type,
            experience_level=opp.experience_level,
            company=CompanyShort(
                id=company.id,
                name=company.name,
                logo_url=company.logo_url,
                city=company.city,
            ),
            location=LocationInfo(
                lat=lat,
                lng=lng,
                address=opp.address,
                city=opp.city,
            ),
            salary=SalaryInfo(
                min=opp.salary_min,
                max=opp.salary_max,
                currency=opp.salary_currency,
                gross=opp.salary_gross,
            ),
            skills=skills,
            tags=tags,
            contact_name=opp.contact_name,
            contact_email=opp.contact_email,
            contact_url=opp.contact_url,
            published_at=opp.published_at,
            expires_at=opp.expires_at,
            event_start_at=opp.event_start_at,
            event_end_at=opp.event_end_at,
            max_participants=opp.max_participants,
            current_participants=opp.current_participants,
            views_count=opp.views_count,
            applications_count=opp.applications_count,
            favorites_count=opp.favorites_count,
            is_favorited=is_favorited,
            is_applied=is_applied,
        )

    async def get_filters(
        self,
        city: str | None = None,
        detected_city: str | None = None,
    ) -> OpportunityFiltersResponse:
        """Доступные фильтры для текущего состояния каталога."""
        filter_data = await self.opportunity_repo.get_filter_options(city=city)

        # Зарплатные диапазоны — фиксированные корзины
        salary_ranges = [
            {"min": None, "max": 50_000, "count": 0},
            {"min": 50_000, "max": 100_000, "count": 0},
            {"min": 100_000, "max": 200_000, "count": 0},
            {"min": 200_000, "max": None, "count": 0},
        ]

        return OpportunityFiltersResponse(
            cities=filter_data["cities"],
            types=filter_data["types"],
            work_formats=filter_data["work_formats"],
            experience_levels=filter_data["experience_levels"],
            employment_types=filter_data["employment_types"],
            salary_ranges=salary_ranges,
            detected_city=detected_city,
        )

    @staticmethod
    def _parse_types(types_str: str | None) -> list[str] | None:
        """
        Разбирает строку "vacancy,event" в список.

        Returns None если types_str не передан (нет фильтра по типу).
        """
        if not types_str:
            return None
        types = [t.strip() for t in types_str.split(",") if t.strip()]
        return types if types else None
