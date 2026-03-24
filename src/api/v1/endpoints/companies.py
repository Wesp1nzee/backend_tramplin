"""
Эндпоинты компаний — финальная версия.

Поток работодателя:
  1. POST /companies/verify-inn          (публичный)    → проверка ИНН, session_token
  2. POST /companies/register            (EMPLOYER)     → создание заявки
  3. POST /companies/me/documents        (EMPLOYER)     → загрузка документов/ссылок
  4. GET  /companies/me/verification     (EMPLOYER)     → текущий статус

Поток куратора:
  5. GET  /companies/pending             (CURATOR)      → список заявок с деталями
  6. POST /companies/{id}/review         (CURATOR)      → апрув / отклонение
"""

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.deps import RoleChecker, get_current_user, get_db
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.company import CompanyRepository
from src.schemas.company import (
    CompanyDocumentsRequest,
    CompanyRegisterRequest,
    CompanyResponse,
    CompanyVerificationDetailResponse,
    CompanyVerificationStatusResponse,
    CuratorReviewRequest,
    InnVerifyRequest,
    InnVerifyResponse,
)
from src.services.company import CompanyService
from src.services.dadata import dadata_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Companies"])

require_employer = RoleChecker([UserRole.EMPLOYER])
require_curator = RoleChecker([UserRole.CURATOR])


# ─── Dependency injection ─────────────────────────────────────


async def get_company_service(db: AsyncSession = Depends(get_db)) -> CompanyService:
    """Инжектируем Redis из token_blacklist — он уже подключён в lifespan."""
    from src.utils.cache import token_blacklist

    redis = token_blacklist._redis  # переиспользуем существующее соединение

    return CompanyService(
        company_repo=CompanyRepository(db),
        dadata=dadata_service,
        redis=redis,
    )


@router.post(
    "/verify-inn",
    response_model=InnVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="[Шаг 1] Проверка ИНН компании",
    description=(
        "Ищет компанию в ЕГРЮЛ/ЕГРИП через Dadata. "
        "Возвращает данные компании для подтверждения пользователем "
        "и **session_token** для следующего шага (действует 30 минут). "
        "\n\n"
        "**Коды ошибок:**\n"
        "- `404 INN_NOT_FOUND` — ИНН не найден\n"
        "- `422 INN_COMPANY_LIQUIDATED` — компания ликвидирована/банкрот\n"
        "- `502 EXTERNAL_SERVICE_ERROR` — Dadata недоступна"
    ),
)
async def verify_inn(
    body: InnVerifyRequest,
    service: CompanyService = Depends(get_company_service),
) -> InnVerifyResponse:
    return await service.verify_inn(body)


@router.post(
    "/register",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Шаг 2] Регистрация компании",
    description=(
        "Создаёт профиль компании и заявку на верификацию (статус **PENDING**). "
        "Требует `session_token` из шага 1 — без него ИНН будет перепроверен через Dadata. "
        "\n\n"
        "**Требует авторизации:** роль `EMPLOYER`."
    ),
    dependencies=[Depends(require_employer)],
)
async def register_company(
    body: CompanyRegisterRequest,
    current_user: User = Depends(get_current_user),
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    return await service.register_company(current_user, body)


# ═════════════════════════════════════════════════════════════
#  ШАГ 3: Загрузка документов и ссылок
# ═════════════════════════════════════════════════════════════


@router.post(
    "/me/documents",
    response_model=CompanyVerificationStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="[Шаг 3] Загрузка документов для верификации",
    description=(
        "Работодатель прикрепляет ссылки (hh.ru, LinkedIn) и документы (PDF). "
        "Можно вызывать несколько раз — данные **накапливаются**, не заменяются. "
        "После отправки куратор получает уведомление. "
        "\n\n"
        "Если заявка была **REJECTED** — переводит её обратно в PENDING."
    ),
    dependencies=[Depends(require_employer)],
)
async def submit_documents(
    body: CompanyDocumentsRequest,
    current_user: User = Depends(get_current_user),
    service: CompanyService = Depends(get_company_service),
) -> CompanyVerificationStatusResponse:
    return await service.submit_documents(current_user, body)


# ═════════════════════════════════════════════════════════════
#  Статус для работодателя
# ═════════════════════════════════════════════════════════════


@router.get(
    "/me/verification",
    response_model=CompanyVerificationStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Статус верификации компании",
    description="Текущий статус + комментарий куратора. Показывать в ЛК работодателя.",
    dependencies=[Depends(require_employer)],
)
async def get_verification_status(
    current_user: User = Depends(get_current_user),
    service: CompanyService = Depends(get_company_service),
) -> CompanyVerificationStatusResponse:
    return await service.get_verification_status(current_user)


# ═════════════════════════════════════════════════════════════
#  Панель куратора
# ═════════════════════════════════════════════════════════════


@router.get(
    "/pending",
    response_model=list[CompanyVerificationDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="[Куратор] Список заявок на верификацию",
    description=(
        "Все компании в статусе **PENDING** с полными данными: "
        "документы, ссылки, данные из ЕГРЮЛ, email работодателя. "
        "Пагинация через `limit` и `offset`."
    ),
    dependencies=[Depends(require_curator)],
)
async def get_pending_companies(
    current_user: User = Depends(get_current_user),
    service: CompanyService = Depends(get_company_service),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CompanyVerificationDetailResponse]:
    return await service.get_pending_companies(current_user, limit=limit, offset=offset)


@router.post(
    "/{company_id}/review",
    response_model=CompanyResponse,
    status_code=status.HTTP_200_OK,
    summary="[Куратор] Верификация / отклонение компании",
    description=(
        "Куратор принимает решение по заявке. "
        "При **апруве** → работодатель может публиковать вакансии. "
        "При **отклонении** → работодатель получает уведомление с комментарием "
        "и может исправить данные и переподать."
    ),
    dependencies=[Depends(require_curator)],
)
async def review_company(
    company_id: str,
    body: CuratorReviewRequest,
    current_user: User = Depends(get_current_user),
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    return await service.curator_review(
        curator=current_user,
        company_id=company_id,
        approve=body.approve,
        comment=body.comment,
    )
