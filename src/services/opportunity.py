"""
Бизнес-логика возможностей (вакансии, стажировки, мероприятия).

Сервис отвечает за:
  - Разбор типов из строки "vacancy,event" → список
  - Делегирование в репозиторий
  - Конвертацию ORM → DTO для детальной карточки
  - Проверку is_active/is_moderated (публичный доступ)
  - CRUD операции для работодателей
"""

from __future__ import annotations

import logging
from uuid import UUID

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import (
    DraftPublishError,
    NotFoundError,
    OpportunityNotFoundError,
    OpportunityValidationError,
)
from src.models.enums import OpportunityStatus, OpportunityType, WorkFormat
from src.models.opportunity import Opportunity
from src.models.user import User
from src.repositories.opportunity import OpportunityRepository
from src.schemas.opportunity import (
    CompanyShort,
    LocationInfo,
    OpportunityCreate,
    OpportunityDetail,
    OpportunityEmployerDetail,
    OpportunityEmployerItem,
    OpportunityEmployerListResponse,
    OpportunityFiltersResponse,
    OpportunityListResponse,
    OpportunityMapResponse,
    OpportunityOwnerStats,
    OpportunityPublishResponse,
    OpportunityUpdate,
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

    # ════════════════════════════════════════════════════════════
    #  Методы для работодателей (Employer CRUD)
    # ════════════════════════════════════════════════════════════

    async def get_employer_opportunities(
        self,
        company_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> OpportunityEmployerListResponse:
        """
        Получить список вакансий работодателя с расширенной статистикой.
        """
        opportunities, total = await self.opportunity_repo.get_employer_opportunities(
            company_id=company_id,
            limit=limit,
            offset=offset,
        )

        items = [self._to_employer_item(opp) for opp in opportunities]

        return OpportunityEmployerListResponse(
            items=items,
            total=total,
        )

    async def get_employer_detail(
        self,
        opportunity_id: UUID,
        company_id: UUID,
    ) -> OpportunityEmployerDetail:
        """
        Получить детальную информацию о вакансии для редактирования.
        Проверяет принадлежность компании.
        """
        opp = await self.opportunity_repo.get_employer_detail(
            opportunity_id=opportunity_id,
            company_id=company_id,
        )

        if not opp:
            raise OpportunityNotFoundError()

        # Извлекаем координаты
        lat, lng = None, None
        if opp.location is not None:
            try:
                lat_result = await self.opportunity_repo.db.execute(
                    select(
                        ST_Y(opp.location),
                        ST_X(opp.location),
                    )
                )
                lat, lng = lat_result.one()
            except SQLAlchemyError, TypeError, ValueError:
                lat, lng = None, None

        # ID навыков и тегов
        skill_ids = [os.skill_id for os in opp.opportunity_skills]
        tag_ids = [ot.tag_id for ot in opp.opportunity_tags]

        # Статистика
        stats = OpportunityOwnerStats(
            views_count=opp.views_count,
            applications_count=opp.applications_count,
            favorites_count=opp.favorites_count,
        )

        return OpportunityEmployerDetail(
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
            salary_min=opp.salary_min,
            salary_max=opp.salary_max,
            salary_currency=opp.salary_currency,
            salary_gross=opp.salary_gross,
            city=opp.city,
            address=opp.address,
            latitude=lat,
            longitude=lng,
            expires_at=opp.expires_at,
            event_start_at=opp.event_start_at,
            event_end_at=opp.event_end_at,
            max_participants=opp.max_participants,
            contact_name=opp.contact_name,
            contact_email=opp.contact_email,
            contact_phone=opp.contact_phone,
            contact_url=opp.contact_url,
            skill_ids=skill_ids,
            tag_ids=tag_ids,
            media=opp.media or [],
            stats=stats,
            created_at=opp.created_at,
            updated_at=opp.updated_at,
            published_at=opp.published_at,
            moderation_comment=opp.moderation_comment,
        )

    async def create_opportunity(
        self,
        company_id: UUID,
        data: OpportunityCreate,
    ) -> OpportunityEmployerDetail:
        """
        Создать новую вакансию/мероприятие.
        """
        # Валидация данных
        self._validate_opportunity_data(data)

        # Подготовка данных для модели
        opp_data = self._prepare_opportunity_data(data)

        # Создаём через репозиторий
        opportunity = await self.opportunity_repo.create_opportunity(
            company_id=company_id,
            data=opp_data,
            skill_ids=data.skill_ids if data.skill_ids else None,
            tag_ids=data.tag_ids if data.tag_ids else None,
        )

        # Возвращаем детальную информацию
        return await self.get_employer_detail(opportunity.id, company_id)

    async def update_opportunity(
        self,
        opportunity_id: UUID,
        company_id: UUID,
        data: OpportunityUpdate,
    ) -> OpportunityEmployerDetail:
        """
        Обновить вакансию/мероприятие.
        """
        # Проверяем существование и принадлежность
        opp = await self.opportunity_repo.get_employer_detail(
            opportunity_id=opportunity_id,
            company_id=company_id,
        )

        if not opp:
            raise OpportunityNotFoundError()

        # Валидация данных
        self._validate_opportunity_data(data)

        # Подготовка данных для обновления
        update_data = self._prepare_update_data(data)

        # Обновляем через репозиторий
        opportunity = await self.opportunity_repo.update_opportunity(
            opportunity=opp,
            data=update_data,
            skill_ids=data.skill_ids,
            tag_ids=data.tag_ids,
        )

        # Возвращаем детальную информацию
        return await self.get_employer_detail(opportunity.id, company_id)

    async def delete_opportunity(
        self,
        opportunity_id: UUID,
        company_id: UUID,
    ) -> None:
        """
        Удалить вакансию/мероприятие (мягкое удаление через статус).
        """
        # Проверяем существование и принадлежность
        opp = await self.opportunity_repo.get_employer_detail(
            opportunity_id=opportunity_id,
            company_id=company_id,
        )

        if not opp:
            raise OpportunityNotFoundError()

        # Удаляем через репозиторий
        await self.opportunity_repo.delete_opportunity(opp)

    async def publish_opportunity(
        self,
        opportunity_id: UUID,
        company_id: UUID,
        requires_moderation: bool = True,
    ) -> OpportunityPublishResponse:
        """
        Опубликовать вакансию (перевод из черновика в ACTIVE).
        """
        # Проверяем существование и принадлежность
        opp = await self.opportunity_repo.get_employer_detail(
            opportunity_id=opportunity_id,
            company_id=company_id,
        )

        if not opp:
            raise OpportunityNotFoundError()

        # Проверка: нельзя опубликовать уже опубликованную
        if opp.status == OpportunityStatus.ACTIVE:
            return OpportunityPublishResponse(
                id=opp.id,
                status=opp.status,
                message="Opportunity is already published",
                requires_moderation=False,
            )

        # Проверка: черновик должен быть заполнен
        if opp.status == OpportunityStatus.DRAFT:
            self._validate_draft_for_publish(opp)

        # Публикуем через репозиторий
        opportunity = await self.opportunity_repo.publish_opportunity(
            opportunity=opp,
            requires_moderation=requires_moderation,
        )

        return OpportunityPublishResponse(
            id=opportunity.id,
            status=opportunity.status,
            message="Opportunity published successfully" if not requires_moderation else "Opportunity sent for moderation",
            requires_moderation=requires_moderation,
        )

    # ─── Вспомогательные методы ────────────────────────────────

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

    @staticmethod
    def _validate_opportunity_data(data: OpportunityCreate | OpportunityUpdate) -> None:
        """
        Валидация данных вакансии/мероприятия.
        """
        # Проверка типа
        if isinstance(data, OpportunityCreate):
            try:
                OpportunityType(data.type)
            except ValueError as e:
                raise OpportunityValidationError(detail=f"Invalid opportunity type: {data.type}") from e

        # Проверка формата работы
        if data.work_format is not None:
            try:
                WorkFormat(data.work_format)
            except ValueError as e:
                raise OpportunityValidationError(detail=f"Invalid work format: {data.work_format}") from e

        # Проверка зарплаты: min <= max
        if hasattr(data, "salary_min") and hasattr(data, "salary_max"):
            if data.salary_min is not None and data.salary_max is not None:
                if data.salary_min > data.salary_max:
                    raise OpportunityValidationError(detail="salary_min cannot be greater than salary_max")

    @staticmethod
    def _prepare_opportunity_data(data: OpportunityCreate) -> dict[str, object]:
        """
        Подготовка данных для создания Opportunity модели.
        """
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point

        opp_data: dict[str, object] = {
            "type": data.type,
            "title": data.title,
            "description": data.description,
            "requirements": data.requirements,
            "responsibilities": data.responsibilities,
            "work_format": data.work_format,
            "employment_type": data.employment_type,
            "experience_level": data.experience_level,
            "salary_min": data.salary_min,
            "salary_max": data.salary_max,
            "salary_currency": data.salary_currency,
            "salary_gross": data.salary_gross,
            "city": data.city,
            "address": data.address,
            "expires_at": data.expires_at,
            "event_start_at": data.event_start_at,
            "event_end_at": data.event_end_at,
            "max_participants": data.max_participants,
            "contact_name": data.contact_name,
            "contact_email": data.contact_email,
            "contact_phone": data.contact_phone,
            "contact_url": data.contact_url,
            "media": data.media,
            "status": OpportunityStatus.DRAFT,
        }

        # Создаём PostGIS геометрию если есть координаты
        if data.latitude is not None and data.longitude is not None:
            point = Point(data.longitude, data.latitude)  # lon, lat для WGS-84
            opp_data["location"] = from_shape(point, srid=4326)

        return opp_data

    @staticmethod
    def _prepare_update_data(data: OpportunityUpdate) -> dict[str, object]:
        """
        Подготовка данных для обновления Opportunity модели.
        """
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point

        opp_data: dict[str, object] = {}

        # Копируем только переданные поля (не None)
        for field in [
            "title",
            "description",
            "requirements",
            "responsibilities",
            "work_format",
            "employment_type",
            "experience_level",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_gross",
            "city",
            "address",
            "expires_at",
            "event_start_at",
            "event_end_at",
            "max_participants",
            "contact_name",
            "contact_email",
            "contact_phone",
            "contact_url",
            "media",
        ]:
            value = getattr(data, field)
            if value is not None:
                opp_data[field] = value

        # Создаём PostGIS геометрию если есть координаты
        if data.latitude is not None and data.longitude is not None:
            point = Point(data.longitude, data.latitude)  # lon, lat для WGS-84
            opp_data["location"] = from_shape(point, srid=4326)

        return opp_data

    @staticmethod
    def _validate_draft_for_publish(opp: Opportunity) -> None:
        """
        Проверка черновика на готовность к публикации.
        """
        required_fields = ["title", "description", "work_format"]
        missing_fields = []

        for field in required_fields:
            if not getattr(opp, field):
                missing_fields.append(field)

        if missing_fields:
            raise DraftPublishError(detail=f"Missing required fields: {', '.join(missing_fields)}")

    @staticmethod
    def _to_employer_item(opp: Opportunity) -> OpportunityEmployerItem:
        """Конвертирует ORM-модель в DTO для списка работодателя."""
        tags = [ot.tag.name for ot in opp.opportunity_tags if ot.tag]

        return OpportunityEmployerItem(
            id=opp.id,
            type=opp.type,
            title=opp.title,
            status=opp.status,
            work_format=opp.work_format,
            employment_type=opp.employment_type,
            experience_level=opp.experience_level,
            location=LocationInfo(
                address=opp.address,
                city=opp.city,
            ),
            salary=SalaryInfo(
                min=opp.salary_min,
                max=opp.salary_max,
                currency=opp.salary_currency,
                gross=opp.salary_gross,
            ),
            tags=tags,
            created_at=opp.created_at,
            published_at=opp.published_at,
            expires_at=opp.expires_at,
            event_start_at=opp.event_start_at,
            event_end_at=opp.event_end_at,
            stats=OpportunityOwnerStats(
                views_count=opp.views_count,
                applications_count=opp.applications_count,
                favorites_count=opp.favorites_count,
            ),
        )
