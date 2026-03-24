"""
Модели компаний и верификации работодателей.

Company           — профиль компании-работодателя.
CompanyVerification — запрос на верификацию с документами.

Логика верификации (авторское решение):
  1. Работодатель регистрируется → статус PENDING
  2. Заполняет верификационную форму (ИНН, корп. почта, ссылки на профсети)
  3. Куратор проверяет и апрувит или отклоняет
  4. Апрув → Company.verification_status = APPROVED
  5. Только апрувнутые компании могут публиковать карточки возможностей
"""

import uuid
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUIDMixin
from src.models.enums import VerificationStatus

if TYPE_CHECKING:
    from src.models.notification import Review
    from src.models.opportunity import Opportunity
    from src.models.social import FavoriteCompany
    from src.models.user import User


class Company(Base, UUIDMixin, TimestampMixin):
    """
    Профиль компании-работодателя.

    Один пользователь с ролью EMPLOYER = одна компания.
    Куратор может редактировать/блокировать компанию.
    """

    __tablename__ = "companies"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    # Основная информация
    name: Mapped[str] = mapped_column(Text, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(Text)  # Юридическое наименование
    inn: Mapped[str | None] = mapped_column(Text, unique=True)  # ИНН
    description: Mapped[str | None] = mapped_column(Text)
    short_description: Mapped[str | None] = mapped_column(Text)  # Для карточек

    # Отрасль и размер
    industry: Mapped[str | None] = mapped_column(Text)
    company_size: Mapped[str | None] = mapped_column(Text)  # "1-10", "11-50", "51-200", "200+"
    founded_year: Mapped[int | None] = mapped_column(Integer)

    # Геолокация
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text, default="Россия")
    address: Mapped[str | None] = mapped_column(Text)
    # PostGIS GEOGRAPHY(Point, 4326) — WGS-84, расстояния в метрах.
    # Пример: ST_DWithin(location, ST_MakePoint(:lon, :lat)::geography, 5000)
    # Создаётся из фронта: ST_MakePoint(longitude, latitude)
    location: Mapped[object | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )

    # Медиа
    logo_url: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text)  # Обложка профиля
    # Дополнительные медиа: фото офиса, видео-презентация
    media: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list, server_default="[]")

    # Контакты и ссылки
    website_url: Mapped[str | None] = mapped_column(Text)
    corporate_email: Mapped[str | None] = mapped_column(Text)
    # {"linkedin": "...", "hh": "...", "telegram": "..."}
    social_links: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")

    # Верификация
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False),
        default=VerificationStatus.PENDING,
    )
    verified_at: Mapped[uuid.UUID | None] = mapped_column()  # timestamp stored as datetime
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    owner: Mapped[User] = relationship("User", back_populates="company", foreign_keys=[owner_id])
    verification_requests: Mapped[list[CompanyVerification]] = relationship(
        "CompanyVerification", back_populates="company", cascade="all, delete-orphan"
    )
    opportunities: Mapped[list[Opportunity]] = relationship(
        "Opportunity", back_populates="company", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[Review]] = relationship(
        "Review",
        back_populates="company",
        primaryjoin="and_(Review.target_id == Company.id, Review.target_type == 'company')",
        foreign_keys="Review.target_id",
        viewonly=True,
    )
    favorited_by: Mapped[list[FavoriteCompany]] = relationship(
        "FavoriteCompany", back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_companies_name", "name"),
        Index("ix_companies_inn", "inn", unique=True),
        Index("ix_companies_industry", "industry"),
        Index("ix_companies_city", "city"),
        Index("ix_companies_city_active", "city", "is_active"),
        Index("ix_companies_verification_status", "verification_status"),
        Index("ix_companies_verification", "verification_status", "is_active"),
        Index("ix_companies_is_active", "is_active"),
        Index("ix_companies_location", "location", postgresql_using="gist"),
    )


class CompanyVerification(Base, UUIDMixin, TimestampMixin):
    """
    Запрос на верификацию компании.

    Авторское решение — многоступенчатая верификация:
    1. ИНН проверяется через Dadata API (уже есть ключи в конфиге)
    2. Корпоративная почта — домен должен совпадать с сайтом компании
    3. Ссылки на профессиональные сети (LinkedIn, hh.ru)
    4. Куратор делает финальный апрув

    История верификаций хранится для аудита.
    """

    __tablename__ = "company_verifications"

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))

    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False),
        default=VerificationStatus.PENDING,
    )

    # Данные верификации
    inn: Mapped[str | None] = mapped_column(Text)
    inn_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # Проверен через Dadata
    corporate_email: Mapped[str | None] = mapped_column(Text)
    email_domain_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Документы и ссылки
    # [{"type": "linkedin", "url": "..."}, {"type": "hh", "url": "..."}]
    verification_links: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Загруженные документы (URL к хранилищу)
    documents: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    # Комментарий куратора
    curator_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Relationships
    company: Mapped[Company] = relationship("Company", back_populates="verification_requests")

    __table_args__ = (
        Index("ix_company_verifications_company", "company_id"),
        Index("ix_company_verifications_status", "status"),
    )
