"""
бизнес-логика регистрации компании.

Ключевое изменение по сравнению с v1:
  Шаг 1 (verify-inn) выдаёт короткоживущий session_token (Redis, TTL 30 мин).
  Шаг 2 (register)   ОБЯЗАН предъявить этот токен — обход невозможен.
  Шаг 3 (submit-docs) — загрузка документов / ссылок в рамках уже созданной заявки.
  Шаг 4  — куратор видит всё в одном месте и принимает решение.

Полный flow:

  POST /companies/verify-inn
    → Dadata ИНН check
    → Redis: store(session_token → inn_data, TTL=1800s)
    → return { ...company_data, session_token }

  POST /companies/register          (EMPLOYER, Bearer)
    body: { session_token, corporate_email, website_url, ... }
    → Redis: get(session_token) — если нет → 422 "Session expired"
    → проверка ИНН занятости
    → create Company(verification_status=PENDING) + CompanyVerification
    → Redis: delete(session_token)
    → return CompanyResponse

  POST /companies/me/documents      (EMPLOYER, Bearer)
    body: { verification_links, description, ... }
    → обновляет CompanyVerification (дополняет документы)
    → нотифицирует кураторов (опционально)

  GET  /companies/me/verification   (EMPLOYER, Bearer)
    → статус + комментарий куратора

  GET  /curator/companies/pending   (CURATOR, Bearer)
    → список всех компаний на верификации с документами

  POST /companies/{id}/review       (CURATOR, Bearer)
    → approve / reject + comment
    → нотификация работодателю (через Notification)
"""

import json
import re
import secrets
import uuid as _uuid

import redis

from src.core.exceptions import AppError, PermissionDeniedError
from src.models.enums import NotificationType, UserRole, VerificationStatus
from src.models.notification import Notification
from src.models.user import User
from src.repositories.company import CompanyRepository
from src.schemas.company import (
    CompanyDocumentsRequest,
    CompanyRegisterRequest,
    CompanyResponse,
    CompanyVerificationDetailResponse,
    CompanyVerificationStatusResponse,
    InnLookupResult,
    InnVerifyRequest,
    InnVerifyResponse,
)
from src.services.dadata import DadataService

# TTL сессионного токена подтверждения ИНН — 30 минут
INN_SESSION_TTL = 1800
INN_SESSION_PREFIX = "inn_session:"


# ─── Доменные ошибки ─────────────────────────────────────────


class CompanyAlreadyExistsError(AppError):
    status_code = 409
    detail = "Company with this INN is already registered"
    error_code = "COMPANY_ALREADY_EXISTS"


class CompanyNotFoundError(AppError):
    status_code = 404
    detail = "Company not found"
    error_code = "COMPANY_NOT_FOUND"


class InnSessionExpiredError(AppError):
    status_code = 422
    detail = "INN verification session expired. Please verify INN again."
    error_code = "INN_SESSION_EXPIRED"


class InnSessionMismatchError(AppError):
    status_code = 422
    detail = "INN in request does not match verified INN in session"
    error_code = "INN_SESSION_MISMATCH"


class CompanyAlreadyApprovedError(AppError):
    status_code = 409
    detail = "Company is already approved"
    error_code = "ALREADY_APPROVED"


# ─── Сервис ──────────────────────────────────────────────────


class CompanyService:
    def __init__(
        self,
        company_repo: CompanyRepository,
        dadata: DadataService,
        redis: redis.asyncio.Redis | None = None,  # инжектируется через DI
    ) -> None:
        self.company_repo = company_repo
        self.dadata = dadata
        self._redis = redis

    # ─────────────────────────────────────────────────────────
    #  ШАГ 1: Проверка ИНН → session_token
    # ─────────────────────────────────────────────────────────

    async def verify_inn(self, request: InnVerifyRequest) -> InnVerifyResponse:
        """
        Проверяет ИНН через Dadata.

        Сохраняет результат в Redis под коротким session_token (TTL 30 мин).
        Фронт передаёт этот токен на шаге 2 — без него регистрация невозможна.

        Если Redis недоступен — работаем без токена (fallback),
        тогда шаг 2 сам перепроверит ИНН через Dadata.
        """
        result: InnLookupResult = await self.dadata.find_company_by_inn(request.inn)

        session_token: str | None = None
        if self._redis:
            session_token = secrets.token_urlsafe(32)
            key = f"{INN_SESSION_PREFIX}{session_token}"
            await self._redis.setex(
                key,
                INN_SESSION_TTL,
                json.dumps(
                    {
                        "inn": result.inn,
                        "kpp": result.kpp,
                        "ogrn": result.ogrn,
                        "full_name": result.full_name,
                        "short_name": result.short_name,
                        "legal_form": result.legal_form,
                        "is_individual": result.is_individual,
                        "status": result.status,
                        "address": result.address,
                        "city": result.city,
                        "ceo_name": result.ceo_name,
                        "okved": result.okved,
                    }
                ),
            )

        return InnVerifyResponse(
            inn=result.inn,
            kpp=result.kpp,
            ogrn=result.ogrn,
            full_name=result.full_name,
            short_name=result.short_name,
            legal_form=result.legal_form,
            is_individual=result.is_individual,
            status=result.status,
            address=result.address,
            city=result.city,
            ceo_name=result.ceo_name,
            ceo_post=result.ceo_post,
            is_verified_by_dadata=True,
            session_token=session_token,
        )

    # ─────────────────────────────────────────────────────────
    #  ШАГ 2: Регистрация компании (session_token обязателен)
    # ─────────────────────────────────────────────────────────

    async def register_company(
        self,
        current_user: User,
        request: CompanyRegisterRequest,
    ) -> CompanyResponse:
        """
        Создаёт Company + CompanyVerification(PENDING).

        Принимает session_token из шага 1 — это гарантирует,
        что ИНН был реально проверен через Dadata в этой сессии.
        Без токена (если Redis был недоступен) — делаем повторный запрос к Dadata.
        """
        if current_user.role != UserRole.EMPLOYER:
            raise PermissionDeniedError(detail="Only employers can register a company")

        if await self.company_repo.get_by_owner(current_user.id):
            raise CompanyAlreadyExistsError("You already have a registered company.")

        if await self.company_repo.get_by_inn(request.inn):
            raise CompanyAlreadyExistsError()

        # Получаем данные Dadata: из Redis (быстро) или повторным запросом
        dadata_result = await self._resolve_dadata(request.inn, request.session_token)

        # Проверяем совпадение ИНН токена с ИНН запроса
        if dadata_result.inn != request.inn:
            raise InnSessionMismatchError()

        # Проверка домена email — предупреждение, не блокировка
        email_domain_verified = False
        if request.website_url:
            email_domain_verified = self._check_email_domain(request.corporate_email, request.website_url)
            if not email_domain_verified:
                pass

        company, _ = await self.company_repo.create_with_verification(
            owner_id=current_user.id,
            dadata_result=dadata_result,
            request=request,
            email_domain_verified=email_domain_verified,
        )

        if self._redis and request.session_token:
            await self._redis.delete(f"{INN_SESSION_PREFIX}{request.session_token}")

        return CompanyResponse.model_validate(company)

    # ─────────────────────────────────────────────────────────
    #  ШАГ 3: Работодатель загружает документы / ссылки
    # ─────────────────────────────────────────────────────────

    async def submit_documents(
        self,
        current_user: User,
        request: CompanyDocumentsRequest,
    ) -> CompanyVerificationStatusResponse:
        """
        Работодатель дополняет заявку документами и ссылками.

        Может вызываться несколько раз — данные накапливаются.
        После успешной отправки нотифицируем кураторов.
        """
        company = await self.company_repo.get_by_owner(current_user.id)
        if not company:
            raise CompanyNotFoundError()

        if company.verification_status == VerificationStatus.APPROVED:
            raise CompanyAlreadyApprovedError()

        verification = await self.company_repo.get_latest_verification(company.id)
        if not verification:
            raise CompanyNotFoundError(detail="Verification request not found")

        existing_links: list[dict[str, str]] = verification.verification_links or []
        new_links = existing_links + [link for link in request.verification_links if link not in existing_links]
        verification.verification_links = new_links

        existing_docs: list[dict[str, str]] = verification.documents or []
        new_docs = existing_docs + [doc for doc in request.documents if doc not in existing_docs]
        verification.documents = new_docs

        if request.description:
            company.description = request.description
        if request.short_description:
            company.short_description = request.short_description

        if company.verification_status == VerificationStatus.REJECTED:
            company.verification_status = VerificationStatus.PENDING
            verification.status = VerificationStatus.PENDING
            verification.curator_comment = None

        await self.company_repo.db.commit()

        # TODO: нотификация кураторам через Notification модель
        # await self._notify_curators(company)

        return CompanyVerificationStatusResponse(
            company_id=company.id,
            verification_status=company.verification_status,
            inn=verification.inn,
            inn_verified=verification.inn_verified,
            email_domain_verified=verification.email_domain_verified,
            curator_comment=verification.curator_comment,
            created_at=verification.created_at,
        )

    # ─────────────────────────────────────────────────────────
    #  Статус для ЛК работодателя
    # ─────────────────────────────────────────────────────────

    async def get_verification_status(
        self,
        current_user: User,
    ) -> CompanyVerificationStatusResponse:
        company = await self.company_repo.get_by_owner(current_user.id)
        if not company:
            raise CompanyNotFoundError()

        verification = await self.company_repo.get_latest_verification(company.id)
        if not verification:
            raise CompanyNotFoundError(detail="No verification request found")

        return CompanyVerificationStatusResponse(
            company_id=company.id,
            verification_status=company.verification_status,
            inn=verification.inn,
            inn_verified=verification.inn_verified,
            email_domain_verified=verification.email_domain_verified,
            curator_comment=verification.curator_comment,
            created_at=verification.created_at,
        )

    # ─────────────────────────────────────────────────────────
    #  Список заявок для куратора
    # ─────────────────────────────────────────────────────────

    async def get_pending_companies(
        self,
        curator: User,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CompanyVerificationDetailResponse]:
        """
        Возвращает компании в статусе PENDING для куратора.
        Каждая запись содержит данные компании + документы верификации.
        """
        if curator.role != UserRole.CURATOR:
            raise PermissionDeniedError()

        return await self.company_repo.get_pending_with_details(limit=limit, offset=offset)

    # ─────────────────────────────────────────────────────────
    #  Решение куратора
    # ─────────────────────────────────────────────────────────

    async def curator_review(
        self,
        curator: User,
        company_id: str,
        approve: bool,
        comment: str | None = None,
    ) -> CompanyResponse:
        """
        Апрув или отклонение верификации.
        После апрува → работодатель может публиковать вакансии.
        После отклонения → работодатель видит комментарий и может переподать.
        """
        if curator.role != UserRole.CURATOR:
            raise PermissionDeniedError()

        try:
            cid = _uuid.UUID(company_id)
        except ValueError as e:
            raise CompanyNotFoundError() from e

        company = await self.company_repo.get(cid)
        if not company:
            raise CompanyNotFoundError()

        new_status = VerificationStatus.APPROVED if approve else VerificationStatus.REJECTED
        company.verification_status = new_status

        verification = await self.company_repo.get_latest_verification(company.id)
        if verification:
            verification.status = new_status
            verification.curator_comment = comment
            verification.reviewed_by_id = curator.id

        # Нотификация работодателю через существующую модель Notification
        notification = Notification(
            recipient_id=company.owner_id,
            type=NotificationType.COMPANY_VERIFIED,
            title="Верификация компании" if approve else "Верификация отклонена",
            body=(
                f"Ваша компания «{company.name}» успешно верифицирована."
                if approve
                else f"Верификация компании «{company.name}» отклонена. Причина: {comment or 'не указана'}"
            ),
            payload={"company_id": str(company.id), "status": new_status},
        )
        self.company_repo.db.add(notification)

        await self.company_repo.db.commit()
        await self.company_repo.db.refresh(company)

        return CompanyResponse.model_validate(company)

    # ─────────────────────────────────────────────────────────
    #  Приватные утилиты
    # ─────────────────────────────────────────────────────────

    async def _resolve_dadata(self, inn: str, session_token: str | None) -> InnLookupResult:
        """
        Берёт данные Dadata из Redis-кэша (если есть session_token)
        или делает новый запрос к Dadata.
        """
        if session_token and self._redis:
            key = f"{INN_SESSION_PREFIX}{session_token}"
            cached = await self._redis.get(key)
            if cached:
                raw = json.loads(cached)
                return InnLookupResult(**raw)
            else:
                # Токен протух — требуем повторную проверку ИНН
                raise InnSessionExpiredError()

        # Fallback: Redis недоступен — идём в Dadata напрямую
        return await self.dadata.find_company_by_inn(inn)

    @staticmethod
    def _check_email_domain(email: str, website_url: str) -> bool:
        try:
            email_domain = email.split("@")[-1].lower().strip()
            site_domain = re.sub(r"^https?://", "", website_url.lower().strip())
            site_domain = re.sub(r"^www\.", "", site_domain)
            site_domain = site_domain.split("/")[0]
            return email_domain == site_domain
        except Exception:
            return False
