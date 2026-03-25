"""
Репозиторий возможностей (вакансии, стажировки, мероприятия, менторство).

Ключевые решения:
  - Используем selectinload для company чтобы избежать N+1
  - Для карты используем ST_X/ST_Y через GeoAlchemy2 — только точки с location IS NOT NULL
  - Фильтрация по типам через IN(), не через LIKE
  - Для публичного листинга показываем только status='active' + is_moderated=True
"""

from __future__ import annotations

import logging
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select
from starlette.requests import Request

from src.core.exceptions import RepositoryError
from src.models.company import Company
from src.models.enums import OpportunityStatus
from src.models.opportunity import Opportunity, OpportunitySkill, OpportunityTag
from src.repositories.base import BaseRepository
from src.schemas.opportunity import (
    CompanyShort,
    LocationInfo,
    OpportunityListItem,
    OpportunityMapMarker,
    SalaryInfo,
)

logger = logging.getLogger(__name__)


def _extract_client_ip(request: Request) -> str:
    """Извлекает реальный IP из заголовков запроса."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


class OpportunityRepository(BaseRepository[Opportunity]):
    model = Opportunity

    def _base_public_query(self) -> Select[tuple[Opportunity]]:
        """
        Базовый запрос для публичного листинга.
        Только активные и промодерированные возможности.
        """
        return (
            select(Opportunity)
            .join(Company, Company.id == Opportunity.company_id)
            .options(selectinload(Opportunity.company))
            .where(
                Opportunity.status == OpportunityStatus.ACTIVE,
                Opportunity.is_moderated == True,  # noqa: E712
                Company.is_active == True,  # noqa: E712
            )
        )

    def _apply_filters(
        self,
        stmt: Select[tuple[Opportunity]],
        *,
        city: str | None = None,
        types: list[str] | None = None,
        work_format: str | None = None,
        experience_level: str | None = None,
        employment_type: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
    ) -> Select[tuple[Opportunity]]:
        """Применяет фильтры к запросу. Возвращает изменённый stmt."""
        if city:
            stmt = stmt.where(Opportunity.city == city)

        if types:
            stmt = stmt.where(Opportunity.type.in_(types))

        if work_format:
            formats = [f.strip() for f in work_format.split(",") if f.strip()]
            if formats:
                stmt = stmt.where(Opportunity.work_format.in_(formats))

        if experience_level:
            levels = [lvl.strip() for lvl in experience_level.split(",") if lvl.strip()]
            if levels:
                stmt = stmt.where(Opportunity.experience_level.in_(levels))

        if employment_type:
            emp_types = [t.strip() for t in employment_type.split(",") if t.strip()]
            if emp_types:
                stmt = stmt.where(Opportunity.employment_type.in_(emp_types))

        if salary_min is not None:
            # Показываем если max >= salary_min ИЛИ min >= salary_min
            stmt = stmt.where((Opportunity.salary_max >= salary_min) | (Opportunity.salary_min >= salary_min))

        if salary_max is not None:
            stmt = stmt.where((Opportunity.salary_min <= salary_max) | (Opportunity.salary_min.is_(None)))

        return stmt

    async def get_public_list(
        self,
        *,
        city: str | None = None,
        types: list[str] | None = None,
        work_format: str | None = None,
        experience_level: str | None = None,
        employment_type: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[OpportunityListItem], int]:
        """
        Публичный список возможностей с пагинацией.

        Returns:
            (items, total) — список карточек и общее количество
        """
        try:
            base = self._apply_filters(
                self._base_public_query(),
                city=city,
                types=types,
                work_format=work_format,
                experience_level=experience_level,
                employment_type=employment_type,
                salary_min=salary_min,
                salary_max=salary_max,
            )

            # Считаем total отдельным запросом
            count_stmt = select(func.count()).select_from(base.subquery())
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar_one() or 0

            # Основной запрос с пагинацией и сортировкой
            items_stmt = base.order_by(Opportunity.published_at.desc()).limit(limit).offset(offset)
            result = await self.db.execute(items_stmt)
            opportunities = list(result.scalars().unique().all())

            items = [self._to_list_item(opp) for opp in opportunities]
            return items, total

        except SQLAlchemyError as e:
            logger.error("OpportunityRepository.get_public_list error: %s", e)
            raise RepositoryError() from e

    async def get_map_markers(
        self,
        *,
        city: str | None = None,
        types: list[str] | None = None,
        work_format: str | None = None,
        experience_level: str | None = None,
        employment_type: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        # Bounding box (опционально, если карта двигается)
        sw_lat: float | None = None,
        sw_lng: float | None = None,
        ne_lat: float | None = None,
        ne_lng: float | None = None,
        limit: int = 500,
    ) -> list[OpportunityMapMarker]:
        """
        Маркеры для React-Leaflet карты.

        Возвращаем только возможности с location IS NOT NULL.
        Кластеризацию делает react-leaflet-cluster на клиенте.
        limit=500 — разумный потолок для карты без деградации браузера.
        """
        try:
            # Извлекаем координаты через PostGIS
            lat_col = func.ST_Y(cast(Opportunity.location, Geometry)).label("lat")
            lng_col = func.ST_X(cast(Opportunity.location, Geometry)).label("lng")

            stmt = (
                select(
                    Opportunity.id,
                    Opportunity.type,
                    Opportunity.title,
                    Opportunity.work_format,
                    Opportunity.city,
                    Opportunity.salary_min,
                    Opportunity.salary_max,
                    Company.name.label("company_name"),
                    Company.logo_url.label("company_logo_url"),
                    lat_col,
                    lng_col,
                )
                .join(Company, Company.id == Opportunity.company_id)
                .where(
                    Opportunity.status == OpportunityStatus.ACTIVE,
                    Opportunity.is_moderated == True,  # noqa: E712
                    Company.is_active == True,  # noqa: E712
                    Opportunity.location.isnot(None),  # только с координатами
                )
            )

            # Применяем все фильтры (единообразно со списком)
            stmt = self._apply_filters(
                stmt,
                city=city,
                types=types,
                work_format=work_format,
                experience_level=experience_level,
                employment_type=employment_type,
                salary_min=salary_min,
                salary_max=salary_max,
            )

            # Bounding box фильтр (когда пользователь двигает карту)
            if all(v is not None for v in [sw_lat, sw_lng, ne_lat, ne_lng]):
                envelope = func.ST_MakeEnvelope(sw_lng, sw_lat, ne_lng, ne_lat, 4326)
                stmt = stmt.where(func.ST_Within(cast(Opportunity.location, Geometry), envelope))

            stmt = stmt.limit(limit)
            result = await self.db.execute(stmt)
            rows = result.all()

            return [
                OpportunityMapMarker(
                    id=row.id,
                    type=row.type,
                    title=row.title,
                    work_format=row.work_format,
                    city=row.city,
                    salary_min=row.salary_min,
                    salary_max=row.salary_max,
                    company_name=row.company_name,
                    company_logo_url=row.company_logo_url,
                    lat=row.lat,
                    lng=row.lng,
                )
                for row in rows
                if row.lat is not None and row.lng is not None  # доп. защита
            ]

        except SQLAlchemyError as e:
            logger.error("OpportunityRepository.get_map_markers error: %s", e)
            raise RepositoryError() from e

    async def get_detail(self, opportunity_id: UUID) -> Opportunity | None:
        """Полная карточка с компанией, навыками и тегами."""
        try:
            result = await self.db.execute(
                select(Opportunity)
                .options(
                    selectinload(Opportunity.company),
                    selectinload(Opportunity.opportunity_skills).selectinload(OpportunitySkill.skill),
                    selectinload(Opportunity.opportunity_tags).selectinload(OpportunityTag.tag),
                )
                .where(Opportunity.id == opportunity_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RepositoryError() from e

    async def increment_views(self, opportunity_id: UUID) -> None:
        """Атомарно увеличивает счётчик просмотров."""
        from sqlalchemy import update

        try:
            await self.db.execute(
                update(Opportunity).where(Opportunity.id == opportunity_id).values(views_count=Opportunity.views_count + 1)
            )
            await self.db.commit()
        except SQLAlchemyError as e:
            logger.warning("Failed to increment views for %s: %s", opportunity_id, e)

    async def get_filter_options(self, city: str | None = None) -> dict[str, list[dict[str, str | int]]]:
        """
        Агрегированные данные для фильтров.
        Один запрос — группировка на стороне БД.
        """
        try:
            base_where = [
                Opportunity.status == OpportunityStatus.ACTIVE,
                Opportunity.is_moderated == True,  # noqa: E712
            ]
            if city:
                base_where.append(Opportunity.city == city)

            # Города
            cities_stmt = (
                select(Opportunity.city, func.count(Opportunity.id).label("cnt"))
                .where(*base_where)
                .where(Opportunity.city.isnot(None))
                .group_by(Opportunity.city)
                .order_by(func.count(Opportunity.id).desc())
                .limit(20)
            )
            cities_result = await self.db.execute(cities_stmt)
            cities = [{"name": row.city, "count": row.cnt} for row in cities_result.all()]

            # Типы
            types_stmt = (
                select(Opportunity.type, func.count(Opportunity.id).label("cnt")).where(*base_where).group_by(Opportunity.type)
            )
            types_result = await self.db.execute(types_stmt)
            types = [{"value": row.type, "label": row.type, "count": row.cnt} for row in types_result.all()]

            # Форматы работы
            formats_stmt = (
                select(Opportunity.work_format, func.count(Opportunity.id).label("cnt"))
                .where(*base_where)
                .group_by(Opportunity.work_format)
            )
            formats_result = await self.db.execute(formats_stmt)
            work_formats = [
                {"value": row.work_format, "label": row.work_format, "count": row.cnt} for row in formats_result.all()
            ]

            # Уровни опыта
            levels_stmt = (
                select(Opportunity.experience_level, func.count(Opportunity.id).label("cnt"))
                .where(*base_where)
                .where(Opportunity.experience_level.isnot(None))
                .group_by(Opportunity.experience_level)
            )
            levels_result = await self.db.execute(levels_stmt)
            experience_levels = [
                {"value": row.experience_level, "label": row.experience_level, "count": row.cnt} for row in levels_result.all()
            ]

            # Типы занятости
            emp_stmt = (
                select(Opportunity.employment_type, func.count(Opportunity.id).label("cnt"))
                .where(*base_where)
                .where(Opportunity.employment_type.isnot(None))
                .group_by(Opportunity.employment_type)
            )
            emp_result = await self.db.execute(emp_stmt)
            employment_types = [
                {"value": row.employment_type, "label": row.employment_type, "count": row.cnt} for row in emp_result.all()
            ]

            return {
                "cities": cities,
                "types": types,
                "work_formats": work_formats,
                "experience_levels": experience_levels,
                "employment_types": employment_types,
            }

        except SQLAlchemyError as e:
            logger.error("OpportunityRepository.get_filter_options error: %s", e)
            raise RepositoryError() from e

    # ─── Конвертеры ORM → DTO ────────────────────────────────

    @staticmethod
    def _to_list_item(opp: Opportunity) -> OpportunityListItem:
        """Маппит ORM-модель в DTO для списка."""
        company = opp.company
        return OpportunityListItem(
            id=opp.id,
            type=opp.type,
            title=opp.title,
            status=opp.status,
            work_format=opp.work_format,
            experience_level=opp.experience_level,
            employment_type=opp.employment_type,
            company=CompanyShort(
                id=company.id,
                name=company.name,
                logo_url=company.logo_url,
                city=company.city,
            ),
            location=LocationInfo(
                # Координаты в списке не нужны — только для карточки
                address=opp.address,
                city=opp.city,
            ),
            salary=SalaryInfo(
                min=opp.salary_min,
                max=opp.salary_max,
                currency=opp.salary_currency,
                gross=opp.salary_gross,
            ),
            tags=[],  # Теги в списке не загружаем — отдельный запрос если нужно
            published_at=opp.published_at,
            expires_at=opp.expires_at,
            event_start_at=opp.event_start_at,
            event_end_at=opp.event_end_at,
            max_participants=opp.max_participants,
            current_participants=opp.current_participants,
            views_count=opp.views_count,
            applications_count=opp.applications_count,
        )
