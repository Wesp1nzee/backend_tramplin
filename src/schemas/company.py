"""
Обновлённые Pydantic-схемы для компаний (v2).

Изменения относительно v1:
  - InnVerifyResponse:          добавлен session_token
  - CompanyRegisterRequest:     добавлен session_token (обязателен)
  - CompanyDocumentsRequest:    новая схема для шага загрузки документов
  - CompanyVerificationDetailResponse: детальный вид для куратора
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Dadata DTO (внутренний) ─────────────────────────────────


class InnLookupResult(BaseModel):
    """Распарсенный результат поиска из Dadata."""

    inn: str
    kpp: str | None = None
    ogrn: str | None = None
    full_name: str
    short_name: str
    legal_form: str | None = None
    is_individual: bool = False
    status: str = "ACTIVE"
    registration_date: int | None = None
    address: str | None = None
    city: str | None = None
    ceo_name: str | None = None
    ceo_post: str | None = None
    okved: str | None = None
    branch_type: str = "MAIN"


class InnVerifyRequest(SchemaBase):
    inn: str = Field("7707083893", description="ИНН: 10 цифр (юрлицо) или 12 цифр (ИП)")

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("INN must contain digits only")
        if len(v) not in (10, 12):
            raise ValueError("INN must be 10 (legal) or 12 (individual) digits")
        return v


class InnVerifyResponse(SchemaBase):
    """
    Ответ после успешной проверки ИНН.
    Включает session_token — одноразовый ключ для шага 2.
    Фронт хранит его в памяти (не в localStorage).
    """

    inn: str
    kpp: str | None
    ogrn: str | None
    full_name: str
    short_name: str
    legal_form: str | None
    is_individual: bool
    status: str
    address: str | None
    city: str | None
    ceo_name: str | None
    ceo_post: str | None
    is_verified_by_dadata: bool = True
    session_token: str | None = Field(
        None,
        description="Передайте в /companies/register. Действует 30 минут.",
    )


class CompanyRegisterRequest(SchemaBase):
    """
    Создание компании — шаг 2 онбординга работодателя.
    session_token из шага 1 обязателен (если Redis доступен).
    """

    inn: str = Field(..., description="ИНН — должен совпадать с токеном сессии")
    session_token: str | None = Field(
        None,
        description=("Токен из POST /verify-inn. Если не передан — ИНН перепроверяется через Dadata."),
    )
    corporate_email: str = Field(..., description="Корпоративный email")
    website_url: str | None = None
    description: str | None = Field(None, max_length=5000)
    short_description: str | None = Field(None, max_length=500)
    industry: str | None = None
    company_size: str | None = Field(
        None,
        description="1-10 | 11-50 | 51-200 | 201-500 | 500+",
    )
    # Ссылки для предварительной верификации (hh, linkedin)
    verification_links: list[dict[str, str]] = Field(
        default_factory=list,
        description='[{"type": "hh", "url": "https://hh.ru/employer/123"}]',
    )

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) not in (10, 12):
            raise ValueError("Invalid INN format")
        return v


# ─── Шаг 3: документы и ссылки ──────────────────────────────


class CompanyDocumentsRequest(SchemaBase):
    """
    Работодатель дополняет заявку документами.
    Может вызываться несколько раз — данные накапливаются (merge, не replace).
    """

    verification_links: list[dict[str, str]] = Field(
        default_factory=list,
        description=('Ссылки для верификации.\nФорматы: {"type": "hh"|"linkedin"|"website"|"other", "url": "..."}'),
        examples=[
            [
                {"type": "hh", "url": "https://hh.ru/employer/3529"},
                {"type": "linkedin", "url": "https://linkedin.com/company/sberbank"},
            ]
        ],
    )
    documents: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Загруженные документы (URL из хранилища S3/MinIO).\n"
            'Форматы: {"type": "certificate"|"license"|"other", "url": "...", "name": "..."}'
        ),
    )
    description: str | None = Field(None, max_length=5000, description="Описание компании")
    short_description: str | None = Field(None, max_length=500)


# ─── Ответы ─────────────────────────────────────────────────


class CompanyVerificationStatusResponse(SchemaBase):
    """Статус верификации для ЛК работодателя."""

    company_id: uuid.UUID
    verification_status: str
    inn: str | None
    inn_verified: bool
    email_domain_verified: bool
    curator_comment: str | None
    created_at: datetime

    # Что ещё нужно сделать (guidance для фронта)
    @property
    def next_step(self) -> str:
        if self.verification_status == "pending":
            return "Ожидает проверки куратором"
        if self.verification_status == "rejected":
            return "Исправьте замечания и переподайте документы"
        if self.verification_status == "approved":
            return "Верификация пройдена"
        return ""


class CompanyVerificationDetailResponse(SchemaBase):
    """
    Детальный вид одной заявки — для панели куратора.
    Содержит всё необходимое для принятия решения без дополнительных запросов.
    """

    company_id: uuid.UUID
    company_name: str
    legal_name: str | None
    inn: str | None
    inn_verified: bool
    ogrn: str | None
    owner_email: str
    corporate_email: str | None
    email_domain_verified: bool
    website_url: str | None
    city: str | None
    industry: str | None
    company_size: str | None
    description: str | None
    verification_links: list[dict[str, str]]
    documents: list[dict[str, str]]
    verification_status: str
    curator_comment: str | None
    submitted_at: datetime


class CompanyResponse(SchemaBase):
    """Публичный профиль компании."""

    id: uuid.UUID
    name: str
    legal_name: str | None
    inn: str | None
    short_description: str | None
    description: str | None
    industry: str | None
    company_size: str | None
    city: str | None
    website_url: str | None
    logo_url: str | None
    verification_status: str
    is_active: bool
    created_at: datetime


# Сырой ответ Dadata (для dev/debug эндпоинта)
class DadataCompanyResponse(BaseModel):
    suggestions: list[dict[str, Any]] = []


class CuratorReviewRequest(BaseModel):
    approve: bool = Field(..., description="true — апрув, false — отклонение")
    comment: str | None = Field(
        None,
        max_length=2000,
        description="Обязателен при отклонении — работодатель увидит этот текст",
    )
