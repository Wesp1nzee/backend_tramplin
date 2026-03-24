"""
Модели карточек возможностей (вакансии, стажировки, менторство, мероприятия) и тегов.

Opportunity   — единая таблица для всех типов карточек.
Tag           — глобальный каталог тегов (системные + пользовательские).
OpportunityTag — связь many-to-many возможностей с тегами.
OpportunitySkill — связь many-to-many возможностей с навыками.

Авторское решение по тегам:
  Теги разделены на 2 типа: системные (is_system=True, создаются разработчиком)
  и пользовательские (добавляются работодателями/кураторами).
  Новые теги работодателей требуют апрува куратора перед появлением в общем списке.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import (
    EmploymentType,
    ExperienceLevel,
    OpportunityStatus,
    OpportunityType,
    WorkFormat,
)

if TYPE_CHECKING:
    from src.models.application import Application, EventRegistration
    from src.models.company import Company
    from src.models.skill import Skill
    from src.models.social import Favorite, Recommendation


class Tag(Base, UUIDMixin, TimestampMixin):
    """
    Теги для категоризации возможностей.

    Помимо тегов-навыков (Python, React) сюда входят
    специальные теги: уровень (Junior), тип занятости (Part-time),
    специализация (Backend, Gamedev) и т.д.
    """

    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(Text, index=True)
    color: Mapped[str | None] = mapped_column(Text)  # HEX цвет для UI-бейджа

    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    opportunity_tags: Mapped[list[OpportunityTag]] = relationship("OpportunityTag", back_populates="tag")


class Opportunity(Base, UUIDMixin, TimestampMixin):
    """
    Карточка возможности: вакансия, стажировка, менторство или мероприятие.

    Единая таблица упрощает поиск и фильтрацию по всем типам одновременно.
    Специфичные поля для мероприятий (дата проведения, макс. участников)
    заполняются только при type=EVENT.
    """

    __tablename__ = "opportunities"

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)

    # Основная информация
    title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)  # Требования к кандидату
    responsibilities: Mapped[str | None] = mapped_column(Text)  # Что предстоит делать

    type: Mapped[OpportunityType] = mapped_column(Enum(OpportunityType, native_enum=False))
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, native_enum=False),
        default=OpportunityStatus.DRAFT,
    )

    # Формат и условия
    work_format: Mapped[WorkFormat] = mapped_column(Enum(WorkFormat, native_enum=False), index=True)
    employment_type: Mapped[EmploymentType | None] = mapped_column(Enum(EmploymentType, native_enum=False))
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(Enum(ExperienceLevel, native_enum=False))

    # Зарплата
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(Text, default="RUB")
    salary_gross: Mapped[bool] = mapped_column(Boolean, default=True)  # До/после налогов

    # Геолокация
    city: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    # PostGIS точка — тот же тип что в Company для единообразия запросов.
    # Для REMOTE/ONLINE вакансий — точка города работодателя.
    # Для OFFICE/HYBRID — точный адрес офиса.
    location: Mapped[object | None] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)

    # Даты
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Для мероприятий (EVENT)
    event_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Запланированная дата публикации (для PLANNED статуса)
    scheduled_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Медиаконтент карточки
    # [{"type": "image", "url": "..."}, {"type": "video", "url": "..."}]
    media: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list, server_default="[]")

    # Контакты для связи
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    contact_url: Mapped[str | None] = mapped_column(Text)  # Ссылка на форму отклика

    # Для мероприятий: максимум участников
    max_participants: Mapped[int | None] = mapped_column(Integer)
    current_participants: Mapped[int] = mapped_column(Integer, default=0)

    # Счётчики
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    applications_count: Mapped[int] = mapped_column(Integer, default=0)
    favorites_count: Mapped[int] = mapped_column(Integer, default=0)

    # Модерация куратором
    is_moderated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    moderated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    moderation_comment: Mapped[str | None] = mapped_column(Text)

    # Relationships
    company: Mapped[Company] = relationship("Company", back_populates="opportunities")
    opportunity_tags: Mapped[list[OpportunityTag]] = relationship(
        "OpportunityTag", back_populates="opportunity", cascade="all, delete-orphan"
    )
    opportunity_skills: Mapped[list[OpportunitySkill]] = relationship(
        "OpportunitySkill", back_populates="opportunity", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        "Application", back_populates="opportunity", cascade="all, delete-orphan"
    )
    favorites: Mapped[list[Favorite]] = relationship("Favorite", back_populates="opportunity", cascade="all, delete-orphan")
    event_registrations: Mapped[list[EventRegistration]] = relationship(
        "EventRegistration", back_populates="opportunity", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        "Recommendation", back_populates="opportunity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_opportunities_type_status", "type", "status"),
        Index("ix_opportunities_city", "city"),
        Index("ix_opportunities_location", "location", postgresql_using="gist"),
        Index("ix_opportunities_salary", "salary_min", "salary_max"),
        Index("ix_opportunities_published", "published_at"),
        Index("ix_opportunities_expires", "expires_at"),
        Index("ix_opportunities_event_start", "event_start_at"),
        Index("ix_opportunities_company_status", "company_id", "status"),
        Index(
            "ix_opportunities_active",
            "status",
            "type",
            postgresql_where="status = 'active'",
        ),
    )


class OpportunityTag(Base, TimestampMixin):
    """Связь карточки возможности с тегом (many-to-many)."""

    __tablename__ = "opportunity_tags"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    opportunity: Mapped[Opportunity] = relationship("Opportunity", back_populates="opportunity_tags")
    tag: Mapped[Tag] = relationship("Tag", back_populates="opportunity_tags")

    __table_args__ = (
        Index("ix_opp_tags_opportunity", "opportunity_id"),
        Index("ix_opp_tags_tag", "tag_id"),
    )


class OpportunitySkill(Base, TimestampMixin):
    """
    Связь карточки возможности с требуемым навыком (many-to-many).
    Отдельно от тегов, чтобы алгоритм матчинга мог сравнивать
    навыки вакансии с навыками профиля.
    """

    __tablename__ = "opportunity_skills"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    # Обязательный или желательный навык
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)

    opportunity: Mapped[Opportunity] = relationship("Opportunity", back_populates="opportunity_skills")
    skill: Mapped[Skill] = relationship("Skill", back_populates="opportunity_skills")

    __table_args__ = (
        Index("ix_opp_skills_opportunity", "opportunity_id"),
        Index("ix_opp_skills_skill", "skill_id"),
    )
