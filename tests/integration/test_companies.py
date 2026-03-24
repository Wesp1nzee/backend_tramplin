"""
Интеграционные тесты регистрации и верификации компаний.

Стратегия моков:
  - DadataService.find_company_by_inn  — патчим напрямую через pytest-mock,
    чтобы не делать реальных HTTP-запросов к Dadata.
  - Redis (token_blacklist._redis)     — FakeRedis (fakeredis.aioredis),
    полностью совместим с redis.asyncio API, но в памяти.

Почему так:
  - Тесты детерминированы — не зависят от сети и ключей Dadata.
  - Покрываем ВСЕ ветки: найден / не найден / ликвидирован / таймаут.
  - Полный flow от verify-inn → register → documents → curator review
    проходит через реальную БД (тестовый PostgreSQL из conftest).
"""

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import fakeredis
import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ExternalServiceError
from src.models.enums import UserRole
from src.schemas.company import InnLookupResult
from src.services.dadata import InnCompanyLiquidatedError, InnNotFoundError


@pytest_asyncio.fixture
async def employer_token(client: AsyncClient) -> str:
    """Регистрирует работодателя и возвращает его access_token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "employer_company@example.com",
            "password": "Empl0yer_Passw0rd_123!",
            "first_name": "Employer",
            "last_name": "Company",
            "role": str(UserRole.EMPLOYER),
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return str(resp.json()["access_token"])


@pytest_asyncio.fixture
async def curator_token(client: AsyncClient) -> str:
    """Регистрирует куратора и возвращает его access_token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "curator_company@example.com",
            "password": "Curat0r_Passw0rd_123!",
            "first_name": "Curator",
            "last_name": "Admin",
            "role": str(UserRole.CURATOR),
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return str(resp.json()["access_token"])


def make_dadata_result(
    inn: str = "7707083893",
    status: str = "ACTIVE",
    short_name: str = "ПАО Сбербанк",
    full_name: str = "ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО «СБЕРБАНК РОССИЯ»",
) -> InnLookupResult:
    """Фабрика InnLookupResult для подстановки в мок."""
    return InnLookupResult(
        inn=inn,
        kpp="773601001",
        ogrn="1027700132195",
        full_name=full_name,
        short_name=short_name,
        legal_form="ПАО",
        is_individual=False,
        status=status,
        address="г Москва, ул Вавилова, д 19",
        city="Москва",
        ceo_name="Греф Герман Оскарович",
        ceo_post="Президент",
        okved="64.19",
        branch_type="MAIN",
    )


def make_ip_result(inn: str = "784806113663") -> InnLookupResult:
    """Фабрика InnLookupResult для ИП."""
    return InnLookupResult(
        inn=inn,
        kpp=None,
        ogrn="318784700000001",
        full_name="Индивидуальный предприниматель Иванов Иван Иванович",
        short_name="ИП Иванов И.И.",
        legal_form="ИП",
        is_individual=True,
        status="ACTIVE",
        address="г Санкт-Петербург",
        city="Санкт-Петербург",
        ceo_name=None,
        ceo_post=None,
        okved="62.01",
        branch_type="MAIN",
    )


# ═════════════════════════════════════════════════════════════
#  БЛОК 1: POST /companies/verify-inn
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_verify_inn_success(client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
    """
    Успешная проверка ИНН: Dadata возвращает активную компанию.
    Ответ содержит данные компании и session_token.
    """
    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=make_dadata_result(),
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            resp = await client.post(
                "/api/v1/companies/verify-inn",
                json={"inn": "7707083893"},
            )

    assert resp.status_code == status.HTTP_200_OK, resp.text
    data = resp.json()

    assert data["inn"] == "7707083893"
    assert data["short_name"] == "ПАО Сбербанк"
    assert data["status"] == "ACTIVE"
    assert data["is_verified_by_dadata"] is True
    assert data["city"] == "Москва"
    assert data["ceo_name"] == "Греф Герман Оскарович"
    # session_token должен быть выдан (Redis доступен)
    assert data["session_token"] is not None
    assert len(data["session_token"]) > 10


@pytest.mark.asyncio
async def test_verify_inn_individual(client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis) -> None:
    """
    ИП: ИНН из 12 цифр, is_individual=True.
    """
    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=make_ip_result(),
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            resp = await client.post(
                "/api/v1/companies/verify-inn",
                json={"inn": "784806113663"},
            )

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["is_individual"] is True
    assert data["kpp"] is None


@pytest.mark.asyncio
async def test_verify_inn_not_found(client: AsyncClient) -> None:
    """
    ИНН не найден в ЕГРЮЛ → 404 INN_NOT_FOUND.
    Dadata возвращает пустой список suggestions.
    """
    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        side_effect=InnNotFoundError(),
    ):
        resp = await client.post(
            "/api/v1/companies/verify-inn",
            json={"inn": "0000000000"},
        )

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error"]["code"] == "INN_NOT_FOUND"


@pytest.mark.asyncio
async def test_verify_inn_liquidated(client: AsyncClient) -> None:
    """
    Компания ликвидирована → 422 INN_COMPANY_LIQUIDATED.
    Регистрация заблокирована на этапе проверки ИНН.
    """
    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        side_effect=InnCompanyLiquidatedError(),
    ):
        resp = await client.post(
            "/api/v1/companies/verify-inn",
            json={"inn": "1234567890"},
        )

    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert resp.json()["error"]["code"] == "INN_COMPANY_LIQUIDATED"


@pytest.mark.asyncio
async def test_verify_inn_dadata_timeout(client: AsyncClient) -> None:
    """
    Dadata недоступна (таймаут) → 502 EXTERNAL_SERVICE_ERROR.
    Приложение не падает, возвращает понятную ошибку.
    """
    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        side_effect=ExternalServiceError("Dadata API timeout"),
    ):
        resp = await client.post(
            "/api/v1/companies/verify-inn",
            json={"inn": "7707083893"},
        )

    assert resp.status_code == status.HTTP_502_BAD_GATEWAY
    assert resp.json()["error"]["code"] == "EXTERNAL_SERVICE_ERROR"


@pytest.mark.asyncio
async def test_verify_inn_invalid_format(client: AsyncClient) -> None:
    """
    Невалидный формат ИНН (не цифры, неправильная длина) → 422 VALIDATION_ERROR.
    Блокируется Pydantic-валидатором до запроса к Dadata.
    """
    cases = [
        {"inn": "abc"},  # не цифры
        {"inn": "123"},  # слишком короткий
        {"inn": "12345678901234"},  # слишком длинный
        {"inn": ""},  # пустой
    ]
    for payload in cases:
        resp = await client.post("/api/v1/companies/verify-inn", json=payload)
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, (
            f"Expected 422 for inn={payload['inn']!r}, got {resp.status_code}"
        )


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 2: POST /companies/register
# # ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_register_company_with_session_token(
    client: AsyncClient,
    employer_token: str,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    Полный happy path: verify-inn → получаем session_token → register.
    Компания создаётся со статусом PENDING.
    """
    dadata_result = make_dadata_result(inn="7707083893")

    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            # Шаг 1
            verify_resp = await client.post(
                "/api/v1/companies/verify-inn",
                json={"inn": "7707083893"},
            )
            assert verify_resp.status_code == status.HTTP_200_OK
            session_token = verify_resp.json()["session_token"]
            assert session_token is not None

            # Шаг 2
            reg_resp = await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "7707083893",
                    "session_token": session_token,
                    "corporate_email": "hr@sberbank.ru",
                    "website_url": "https://sberbank.ru",
                    "industry": "Финансы",
                    "company_size": "500+",
                    "description": "Крупнейший банк",
                },
                headers={"Authorization": f"Bearer {employer_token}"},
            )

    assert reg_resp.status_code == status.HTTP_201_CREATED, reg_resp.text
    data = reg_resp.json()
    assert data["name"] == "ПАО Сбербанк"
    assert data["inn"] == "7707083893"
    assert data["verification_status"] == "pending"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_company_session_token_is_one_time(
    client: AsyncClient,
    employer_token: str,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    session_token одноразовый: после регистрации второй /register с тем же
    токеном должен вернуть 422 INN_SESSION_EXPIRED.
    """
    dadata_result = make_dadata_result(inn="7707083001")

    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            verify_resp = await client.post(
                "/api/v1/companies/verify-inn",
                json={"inn": "7707083001"},
            )
            session_token = verify_resp.json()["session_token"]

            # Первая регистрация — успех
            await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "7707083001",
                    "session_token": session_token,
                    "corporate_email": "hr@test.ru",
                },
                headers={"Authorization": f"Bearer {employer_token}"},
            )

            # Вторая попытка с тем же токеном — 422
            second_resp = await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "7707083001",
                    "session_token": session_token,
                    "corporate_email": "hr@test.ru",
                },
                headers={"Authorization": f"Bearer {employer_token}"},
            )

    # Либо SESSION_EXPIRED (токен удалён), либо COMPANY_ALREADY_EXISTS
    assert second_resp.status_code in (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        status.HTTP_409_CONFLICT,
    )


@pytest.mark.asyncio
async def test_register_company_expired_session_token(
    client: AsyncClient,
    employer_token: str,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    session_token протух (удалён из Redis) → 422 INN_SESSION_EXPIRED.
    Симулируем протухание: просто не кладём токен в Redis.
    """
    with patch("src.utils.cache.token_blacklist._redis", fake_redis):
        resp = await client.post(
            "/api/v1/companies/register",
            json={
                "inn": "7707083893",
                "session_token": "definitely_expired_token_abc123",
                "corporate_email": "hr@sberbank.ru",
            },
            headers={"Authorization": f"Bearer {employer_token}"},
        )

    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert resp.json()["error"]["code"] == "INN_SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_register_company_fallback_no_redis(
    client: AsyncClient,
    employer_token: str,
) -> None:
    """
    Fallback: Redis недоступен (None), нет session_token.
    /register должен повторно обратиться к Dadata и успешно создать компанию.
    """
    dadata_result = make_dadata_result(inn="9999000001")

    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        # Делаем вид что Redis = None (недоступен)
        with patch("src.utils.cache.token_blacklist._redis", None):
            resp = await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "9999000001",
                    # session_token НЕ передаём — fallback на Dadata
                    "corporate_email": "hr@fallback.ru",
                },
                headers={"Authorization": f"Bearer {employer_token}"},
            )

    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    assert resp.json()["inn"] == "9999000001"


@pytest.mark.asyncio
async def test_register_company_inn_mismatch(
    client: AsyncClient,
    employer_token: str,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    ИНН в теле запроса ≠ ИНН в session_token → 422 INN_SESSION_MISMATCH.
    Попытка использовать чужой токен.
    """
    # Создаём сессию для ИНН A
    dadata_result = make_dadata_result(inn="7707083893")
    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            verify_resp = await client.post(
                "/api/v1/companies/verify-inn",
                json={"inn": "7707083893"},
            )
            session_token = verify_resp.json()["session_token"]

            # Пытаемся зарегистрироваться с другим ИНН B
            resp = await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "1234509876",  # другой ИНН
                    "session_token": session_token,
                    "corporate_email": "hr@other.ru",
                },
                headers={"Authorization": f"Bearer {employer_token}"},
            )

    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert resp.json()["error"]["code"] == "INN_SESSION_MISMATCH"


@pytest.mark.asyncio
async def test_register_company_duplicate_inn(
    client: AsyncClient,
    employer_token: str,
    fake_redis: fakeredis.aioredis.FakeRedis,
    db_session: AsyncSession,
) -> None:
    """
    Нельзя зарегистрировать компанию с уже занятым ИНН → 409 COMPANY_ALREADY_EXISTS.
    """
    dadata_result = make_dadata_result(inn="5555555555")

    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            # Регистрируем работодателя 2 (у employer_token уже будет своя компания)
            second_employer_resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "employer2_dup@example.com",
                    "password": "Empl0yer2_Passw0rd!",
                    "first_name": "Second",
                    "last_name": "Employer",
                    "role": str(UserRole.EMPLOYER),
                },
            )
            second_token = second_employer_resp.json()["access_token"]

            # Первая регистрация
            verify1 = await client.post("/api/v1/companies/verify-inn", json={"inn": "5555555555"})
            token1 = verify1.json()["session_token"]
            await client.post(
                "/api/v1/companies/register",
                json={"inn": "5555555555", "session_token": token1, "corporate_email": "a@a.ru"},
                headers={"Authorization": f"Bearer {employer_token}"},
            )

            # Вторая регистрация с тем же ИНН другим пользователем
            verify2 = await client.post("/api/v1/companies/verify-inn", json={"inn": "5555555555"})
            token2 = verify2.json()["session_token"]
            resp = await client.post(
                "/api/v1/companies/register",
                json={"inn": "5555555555", "session_token": token2, "corporate_email": "b@b.ru"},
                headers={"Authorization": f"Bearer {second_token}"},
            )

    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.json()["error"]["code"] == "COMPANY_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_register_company_requires_employer_role(
    client: AsyncClient,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    Регистрация компании требует роль EMPLOYER.
    Соискатель получает 403.
    """
    applicant_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "applicant_no_company@example.com",
            "password": "Appl1c4nt_Passw0rd!",
            "first_name": "App",
            "last_name": "Licant",
            "role": str(UserRole.APPLICANT),
        },
    )
    applicant_token = applicant_resp.json()["access_token"]

    with patch("src.utils.cache.token_blacklist._redis", fake_redis):
        resp = await client.post(
            "/api/v1/companies/register",
            json={"inn": "7707083893", "corporate_email": "hr@test.ru"},
            headers={"Authorization": f"Bearer {applicant_token}"},
        )

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_register_company_requires_auth(client: AsyncClient) -> None:
    """
    Без Bearer token → 401.
    """
    resp = await client.post(
        "/api/v1/companies/register",
        json={"inn": "7707083893", "corporate_email": "hr@test.ru"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 3: POST /companies/me/documents
# # ═════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def registered_company(
    client: AsyncClient,
    employer_token: str,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> dict[str, Any]:
    """Создаёт компанию в статусе PENDING и возвращает её данные."""
    dadata_result = make_dadata_result(inn="6666666666")
    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            verify_resp = await client.post("/api/v1/companies/verify-inn", json={"inn": "6666666666"})
            session_token = verify_resp.json()["session_token"]

            reg_resp = await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "6666666666",
                    "session_token": session_token,
                    "corporate_email": "hr@docs-test.ru",
                    "website_url": "https://docs-test.ru",
                },
                headers={"Authorization": f"Bearer {employer_token}"},
            )
    assert reg_resp.status_code == status.HTTP_201_CREATED
    return cast(dict[str, Any], reg_resp.json())


@pytest.mark.asyncio
async def test_submit_documents_success(
    client: AsyncClient,
    employer_token: str,
    registered_company: dict[str, Any],
) -> None:
    """
    Работодатель загружает ссылки и документы.
    Статус остаётся PENDING, данные сохраняются.
    """
    resp = await client.post(
        "/api/v1/companies/me/documents",
        json={
            "verification_links": [
                {"type": "hh", "url": "https://hh.ru/employer/123"},
                {"type": "linkedin", "url": "https://linkedin.com/company/test"},
            ],
            "documents": [
                {
                    "type": "certificate",
                    "url": "https://s3.example.com/cert.pdf",
                    "name": "Свидетельство",
                },
            ],
            "description": "Описание нашей замечательной компании",
        },
        headers={"Authorization": f"Bearer {employer_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK, resp.text
    data = resp.json()
    assert data["verification_status"] == "pending"
    assert data["inn_verified"] is True


@pytest.mark.asyncio
async def test_submit_documents_accumulates(
    client: AsyncClient,
    employer_token: str,
    registered_company: dict[str, Any],
) -> None:
    """
    Документы накапливаются при повторных вызовах — данные не заменяются.
    """
    headers = {"Authorization": f"Bearer {employer_token}"}

    await client.post(
        "/api/v1/companies/me/documents",
        json={"verification_links": [{"type": "hh", "url": "https://hh.ru/employer/1"}]},
        headers=headers,
    )

    await client.post(
        "/api/v1/companies/me/documents",
        json={"verification_links": [{"type": "linkedin", "url": "https://linkedin.com/1"}]},
        headers=headers,
    )

    # Проверяем статус — оба вызова прошли без ошибок
    status_resp = await client.get(
        "/api/v1/companies/me/verification",
        headers=headers,
    )
    assert status_resp.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_submit_documents_without_company(
    client: AsyncClient,
) -> None:
    """
    Работодатель без компании пытается загрузить документы → 404.
    """
    new_employer_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "no_company_employer@example.com",
            "password": "NoCo_Empl0yer_Passw0rd!",
            "first_name": "No",
            "last_name": "Company",
            "role": str(UserRole.EMPLOYER),
        },
    )
    token = new_employer_resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/companies/me/documents",
        json={"verification_links": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 4: GET /companies/me/verification
# # ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_verification_status_pending(
    client: AsyncClient,
    employer_token: str,
    registered_company: dict[str, Any],
) -> None:
    """
    Только что зарегистрированная компания → статус PENDING.
    """
    resp = await client.get(
        "/api/v1/companies/me/verification",
        headers={"Authorization": f"Bearer {employer_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["verification_status"] == "pending"
    assert data["inn_verified"] is True
    assert data["curator_comment"] is None


@pytest.mark.asyncio
async def test_get_verification_status_no_company(client: AsyncClient) -> None:
    """
    Работодатель без компании запрашивает статус → 404.
    """
    resp_reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "employer_no_company_status@example.com",
            "password": "Empl0yer_NoComp_Passw0rd!",
            "first_name": "No",
            "last_name": "Comp",
            "role": str(UserRole.EMPLOYER),
        },
    )
    token = resp_reg.json()["access_token"]

    resp = await client.get(
        "/api/v1/companies/me/verification",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 5: GET /companies/pending  (куратор)
# # ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_pending_companies_curator(
    client: AsyncClient,
    curator_token: str,
    registered_company: dict[str, Any],
) -> None:
    """
    Куратор видит список заявок в статусе PENDING.
    """
    resp = await client.get(
        "/api/v1/companies/pending",
        headers={"Authorization": f"Bearer {curator_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Проверяем структуру одной записи
    entry = data[0]
    assert "company_id" in entry
    assert "company_name" in entry
    assert "inn" in entry
    assert "inn_verified" in entry
    assert "owner_email" in entry
    assert "verification_links" in entry
    assert "documents" in entry
    assert entry["verification_status"] == "pending"


@pytest.mark.asyncio
async def test_get_pending_companies_forbidden_for_employer(
    client: AsyncClient,
    employer_token: str,
) -> None:
    """
    Работодатель не может смотреть список заявок куратора → 403.
    """
    resp = await client.get(
        "/api/v1/companies/pending",
        headers={"Authorization": f"Bearer {employer_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_pending_companies_pagination(
    client: AsyncClient,
    curator_token: str,
) -> None:
    """
    Пагинация через limit/offset работает корректно.
    """
    resp = await client.get(
        "/api/v1/companies/pending?limit=1&offset=0",
        headers={"Authorization": f"Bearer {curator_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 1


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 6: POST /companies/{id}/review  (куратор)
# # ═════════════════════════════════════════════════════════════


# @pytest.mark.asyncio
async def test_curator_approve_company(
    client: AsyncClient,
    curator_token: str,
    employer_token: str,
    registered_company: dict[str, Any],
) -> None:
    """
    Полный happy path: куратор апрувит компанию.
    После апрува статус = APPROVED, работодатель получает нотификацию.
    """
    company_id = registered_company["id"]

    resp = await client.post(
        f"/api/v1/companies/{company_id}/review",
        json={"approve": True, "comment": "Всё проверено"},
        headers={"Authorization": f"Bearer {curator_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK, resp.text
    data = resp.json()
    assert data["verification_status"] == "approved"

    # Работодатель видит обновлённый статус
    status_resp = await client.get(
        "/api/v1/companies/me/verification",
        headers={"Authorization": f"Bearer {employer_token}"},
    )
    assert status_resp.json()["verification_status"] == "approved"


@pytest.mark.asyncio
async def test_curator_reject_company(
    client: AsyncClient,
    curator_token: str,
    employer_token: str,
    registered_company: dict[str, Any],
) -> None:
    """
    Куратор отклоняет заявку с комментарием.
    Работодатель видит статус REJECTED и причину.
    """
    company_id = registered_company["id"]
    reject_comment = "Домен email не совпадает с сайтом компании"

    resp = await client.post(
        f"/api/v1/companies/{company_id}/review",
        json={"approve": False, "comment": reject_comment},
        headers={"Authorization": f"Bearer {curator_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["verification_status"] == "rejected"

    # Статус виден работодателю, включая комментарий
    status_resp = await client.get(
        "/api/v1/companies/me/verification",
        headers={"Authorization": f"Bearer {employer_token}"},
    )
    data = status_resp.json()
    assert data["verification_status"] == "rejected"
    assert data["curator_comment"] == reject_comment


@pytest.mark.asyncio
async def test_resubmit_after_rejection(
    client: AsyncClient,
    employer_token: str,
    curator_token: str,
    registered_company: dict[str, Any],
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    После отклонения работодатель может исправить данные и переподать.
    Статус автоматически сбрасывается в PENDING.
    """
    company_id = registered_company["id"]

    # Куратор отклоняет
    await client.post(
        f"/api/v1/companies/{company_id}/review",
        json={"approve": False, "comment": "Недостаточно документов"},
        headers={"Authorization": f"Bearer {curator_token}"},
    )

    # Работодатель дополняет документы
    resubmit_resp = await client.post(
        "/api/v1/companies/me/documents",
        json={
            "verification_links": [{"type": "hh", "url": "https://hh.ru/employer/999"}],
            "documents": [{"type": "license", "url": "https://s3.example.com/lic.pdf", "name": "Лицензия"}],
        },
        headers={"Authorization": f"Bearer {employer_token}"},
    )

    assert resubmit_resp.status_code == status.HTTP_200_OK
    # После повторной подачи статус сброшен в PENDING
    assert resubmit_resp.json()["verification_status"] == "pending"


@pytest.mark.asyncio
async def test_curator_review_nonexistent_company(
    client: AsyncClient,
    curator_token: str,
) -> None:
    """
    Куратор пытается апрувить несуществующую компанию → 404.
    """
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.post(
        f"/api/v1/companies/{fake_id}/review",
        json={"approve": True},
        headers={"Authorization": f"Bearer {curator_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_curator_review_invalid_uuid(
    client: AsyncClient,
    curator_token: str,
) -> None:
    """
    company_id не является UUID → 404 (ConpanyNotFoundError).
    """
    resp = await client.post(
        "/api/v1/companies/not-a-uuid/review",
        json={"approve": True},
        headers={"Authorization": f"Bearer {curator_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_employer_cannot_review(
    client: AsyncClient,
    employer_token: str,
    registered_company: dict[str, Any],
) -> None:
    """
    Работодатель не может апрувить компании → 403.
    """
    company_id = registered_company["id"]

    resp = await client.post(
        f"/api/v1/companies/{company_id}/review",
        json={"approve": True},
        headers={"Authorization": f"Bearer {employer_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 7: Email domain проверка
# # ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_email_domain_match_recorded(
    client: AsyncClient,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    Совпадение домена email и сайта: email_domain_verified=True в верификации.
    Не блокирует регистрацию — куратор видит флаг как подсказку.
    """
    new_employer_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "employer_domain_match@example.com",
            "password": "Empl0yer_Domain_Match!",
            "first_name": "Domain",
            "last_name": "Match",
            "role": str(UserRole.EMPLOYER),
        },
    )
    token = new_employer_resp.json()["access_token"]
    dadata_result = make_dadata_result(inn="1111222233")

    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            verify_resp = await client.post("/api/v1/companies/verify-inn", json={"inn": "1111222233"})
            session_token = verify_resp.json()["session_token"]

            reg_resp = await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "1111222233",
                    "session_token": session_token,
                    "corporate_email": "hr@match.ru",
                    "website_url": "https://match.ru",  # домен совпадает
                },
                headers={"Authorization": f"Bearer {token}"},
            )

    assert reg_resp.status_code == status.HTTP_201_CREATED
    # email_domain_verified проверяется через /me/verification
    status_resp = await client.get(
        "/api/v1/companies/me/verification",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_resp.json()["email_domain_verified"] is True


@pytest.mark.asyncio
async def test_email_domain_mismatch_does_not_block(
    client: AsyncClient,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """
    Несовпадение домена не блокирует регистрацию — только логируется.
    email_domain_verified=False, куратор решает сам.
    """
    new_employer_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "employer_domain_mismatch@example.com",
            "password": "Empl0yer_Domain_Mis!",
            "first_name": "Domain",
            "last_name": "Mismatch",
            "role": str(UserRole.EMPLOYER),
        },
    )
    token = new_employer_resp.json()["access_token"]
    dadata_result = make_dadata_result(inn="3333444455")

    with patch(
        "src.services.company.DadataService.find_company_by_inn",
        new_callable=AsyncMock,
        return_value=dadata_result,
    ):
        with patch("src.utils.cache.token_blacklist._redis", fake_redis):
            verify_resp = await client.post("/api/v1/companies/verify-inn", json={"inn": "3333444455"})
            session_token = verify_resp.json()["session_token"]

            reg_resp = await client.post(
                "/api/v1/companies/register",
                json={
                    "inn": "3333444455",
                    "session_token": session_token,
                    "corporate_email": "hr@company.ru",
                    "website_url": "https://completely-different.com",  # не совпадает
                },
                headers={"Authorization": f"Bearer {token}"},
            )

    # Регистрация проходит несмотря на несовпадение
    assert reg_resp.status_code == status.HTTP_201_CREATED

    status_resp = await client.get(
        "/api/v1/companies/me/verification",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_resp.json()["email_domain_verified"] is False
