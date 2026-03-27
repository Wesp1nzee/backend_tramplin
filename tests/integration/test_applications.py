"""
Интеграционные тесты API откликов (Applications).

Тестируются эндпоинты:
  Для соискателя (APPLICANT):
    - POST   /applications            → Создать отклик
    - GET    /applications/me         → Список моих откликов
    - GET    /applications/me/{id}    → Детали моего отклика
    - DELETE /applications/me/{id}    → Отозвать отклик

  Для работодателя (EMPLOYER):
    - GET    /opportunities/{id}/applications → Список откликов на вакансию
    - GET    /applications/{id}               → Детали отклика
    - PATCH  /applications/{id}/status        → Смена статуса
    - PATCH  /applications/{id}/feedback      → Обратная связь

Стратегия:
  - Создаём пользователей (соискатель, работодатель)
  - Создаём компанию и вакансию
  - Тестируем все сценарии создания, просмотра, обновления откликов
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import hash_password
from src.models.application import Application
from src.models.company import Company
from src.models.enums import ApplicationStatus, OpportunityStatus, VerificationStatus
from src.models.opportunity import Opportunity
from src.models.user import Profile, User


@pytest_asyncio.fixture
async def test_applicant(db_session: AsyncSession) -> User:
    """Создаёт тестового соискателя."""
    applicant = User(
        email="applicant@test.ru",
        hashed_password=hash_password("test_password"),
        role="applicant",
        is_active=True,
        is_verified=True,
        profile=Profile(
            first_name="Иван",
            last_name="Петров",
            middle_name="Иванович",
            headline="Python Разработчик",
            university="МГУ",
            graduation_year=2024,
            cv_url="https://example.com/cv/ivan_petrov.pdf",
            privacy_settings={
                "public_profile": True,
                "show_contacts": False,
                "show_github": True,
                "show_applications": False,
            },
        ),
    )
    db_session.add(applicant)
    await db_session.commit()

    # Reload with profile to avoid lazy loading
    result = await db_session.execute(select(User).options(selectinload(User.profile)).where(User.id == applicant.id))
    applicant = result.scalar_one()
    return applicant


@pytest_asyncio.fixture
async def test_employer(db_session: AsyncSession) -> User:
    """Создаёт тестового работодателя."""
    employer = User(
        email="employer@test.ru",
        hashed_password=hash_password("test_password"),
        role="employer",
        is_active=True,
        is_verified=True,
        profile=Profile(first_name="Алексей", last_name="Смирнов"),
    )
    db_session.add(employer)
    await db_session.commit()
    await db_session.refresh(employer)
    return employer


@pytest_asyncio.fixture
async def test_company(db_session: AsyncSession, test_employer: User) -> Company:
    """Создаёт тестовую компанию."""
    company = Company(
        owner_id=test_employer.id,
        name="IT Компания",
        inn="7707083893",
        corporate_email="hr@it-company.ru",
        website_url="https://it-company.ru",
        city="Москва",
        is_active=True,
        verification_status=VerificationStatus.APPROVED,
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    return company


@pytest_asyncio.fixture
async def test_opportunity(db_session: AsyncSession, test_company: Company) -> Opportunity:
    """Создаёт тестовую вакансию."""
    now = datetime.utcnow()
    opportunity = Opportunity(
        type="vacancy",
        title="Python Backend Разработчик",
        description="Разработка backend для банковских систем",
        requirements="Python 3.11+, FastAPI, PostgreSQL",
        responsibilities="Разработка новых фич, код-ревью",
        status=OpportunityStatus.ACTIVE,
        is_moderated=True,
        work_format="hybrid",
        experience_level="middle",
        employment_type="full_time",
        salary_min=150000,
        salary_max=250000,
        salary_currency="RUB",
        salary_gross=True,
        city="Москва",
        address="ул. Вавилова, д 19",
        published_at=now,
        expires_at=now + timedelta(days=30),
        company_id=test_company.id,
    )
    db_session.add(opportunity)
    await db_session.commit()
    await db_session.refresh(opportunity)
    return opportunity


@pytest_asyncio.fixture
async def test_application(
    db_session: AsyncSession,
    test_opportunity: Opportunity,
    test_applicant: User,
) -> Application:
    """Создаёт тестовый отклик."""
    application = Application(
        opportunity_id=test_opportunity.id,
        applicant_id=test_applicant.profile.id,
        status=ApplicationStatus.PENDING,
        cover_letter="Очень хочу работать у вас!",
        cv_url_snapshot=test_applicant.profile.cv_url,
        status_history=[
            {
                "status": "pending",
                "changed_at": datetime.now(UTC).isoformat(),
                "changed_by": "applicant",
            }
        ],
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


async def _login_user(client: AsyncClient, email: str, password: str) -> str:
    """Вспомогательная функция для логина и получения токена."""
    login_data = {"username": email, "password": password}
    resp = await client.post("/api/v1/auth/login", data=login_data)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    return data["access_token"]  # type: ignore[no-any-return]


# ═════════════════════════════════════════════════════════════
#  БЛОК 1: POST /applications (Создание отклика)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_application_success(
    client: AsyncClient,
    test_applicant: User,
    test_opportunity: Opportunity,
) -> None:
    """Успешное создание отклика соискателем."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    application_data = {
        "opportunity_id": str(test_opportunity.id),
        "cover_letter": "Здравствуйте! Хочу работать у вас Python разработчиком.",
    }

    resp = await client.post("/api/v1/applications", json=application_data, headers=headers)
    assert resp.status_code == status.HTTP_201_CREATED

    data = resp.json()
    assert data["opportunity_id"] == str(test_opportunity.id)
    assert data["status"] == "pending"
    assert data["cover_letter"] == application_data["cover_letter"]
    assert data["cv_url_snapshot"] == test_applicant.profile.cv_url
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_application_without_cover_letter(
    client: AsyncClient,
    test_applicant: User,
    test_opportunity: Opportunity,
) -> None:
    """Создание отклика без сопроводительного письма."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    application_data = {
        "opportunity_id": str(test_opportunity.id),
    }

    resp = await client.post("/api/v1/applications", json=application_data, headers=headers)
    assert resp.status_code == status.HTTP_201_CREATED

    data = resp.json()
    assert data["cover_letter"] is None


@pytest.mark.asyncio
async def test_create_application_duplicate(
    client: AsyncClient,
    test_applicant: User,
    test_opportunity: Opportunity,
    test_application: Application,
) -> None:
    """Попытка создать дублирующийся отклик."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    application_data = {
        "opportunity_id": str(test_opportunity.id),
        "cover_letter": "Повторный отклик",
    }

    resp = await client.post("/api/v1/applications", json=application_data, headers=headers)
    assert resp.status_code == status.HTTP_409_CONFLICT

    data = resp.json()
    assert data["error"]["code"] == "APPLICATION_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_create_application_inactive_opportunity(
    client: AsyncClient,
    test_applicant: User,
    test_company: Company,
    db_session: AsyncSession,
) -> None:
    """Попытка отклика на неактивную вакансию."""
    # Создаём неактивную вакансию
    inactive_opp = Opportunity(
        type="vacancy",
        title="Неактивная вакансия",
        status=OpportunityStatus.DRAFT,
        is_moderated=False,
        work_format="remote",
        city="Москва",
        company_id=test_company.id,
    )
    db_session.add(inactive_opp)
    await db_session.commit()

    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    application_data = {
        "opportunity_id": str(inactive_opp.id),
    }

    resp = await client.post("/api/v1/applications", json=application_data, headers=headers)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    data = resp.json()
    assert data["error"]["code"] == "OPPORTUNITY_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_create_application_unverified_company(
    client: AsyncClient,
    test_applicant: User,
    db_session: AsyncSession,
) -> None:
    """Попытка отклика на вакансию неверифицированной компании."""
    # Создаём компанию с pending верификацией
    result = await db_session.execute(select(User).where(User.role == "employer").limit(1))
    employer_user = result.scalar_one_or_none()

    unverified_company = Company(
        owner_id=employer_user.id if employer_user else test_applicant.id,
        name="Неверифицированная компания",
        inn="9999999999",
        city="Москва",
        verification_status=VerificationStatus.PENDING,
        is_active=True,
    )
    db_session.add(unverified_company)
    await db_session.flush()

    # Создаём вакансию
    opportunity = Opportunity(
        type="vacancy",
        title="Вакансия в неверифицированной компании",
        status=OpportunityStatus.ACTIVE,
        is_moderated=True,
        work_format="remote",
        city="Москва",
        company_id=unverified_company.id,
    )
    db_session.add(opportunity)
    await db_session.commit()

    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    application_data = {
        "opportunity_id": str(opportunity.id),
    }

    resp = await client.post("/api/v1/applications", json=application_data, headers=headers)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    data = resp.json()
    assert data["error"]["code"] == "COMPANY_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_create_application_unauthorized(
    client: AsyncClient,
    test_opportunity: Opportunity,
) -> None:
    """Попытка создать отклик без авторизации."""
    application_data = {
        "opportunity_id": str(test_opportunity.id),
    }

    resp = await client.post("/api/v1/applications", json=application_data)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ═════════════════════════════════════════════════════════════
#  БЛОК 2: GET /applications/me (Список откликов соискателя)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_my_applications_success(
    client: AsyncClient,
    test_applicant: User,
    test_opportunity: Opportunity,
    test_application: Application,
) -> None:
    """Успешное получение списка своих откликов."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/applications/me", headers=headers)
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["id"] == str(test_application.id)
    assert item["status"] == "pending"
    assert item["opportunity_id"] == str(test_opportunity.id)


@pytest.mark.asyncio
async def test_get_my_applications_empty(
    client: AsyncClient,
    test_applicant: User,
) -> None:
    """Получение списка откликов когда их нет."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/applications/me", headers=headers)
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_get_my_applications_pagination(
    client: AsyncClient,
    test_applicant: User,
    test_company: Company,
    db_session: AsyncSession,
) -> None:
    """Тест пагинации списка откликов."""
    # Создаём несколько вакансий для тестов пагинации
    opportunities = []
    for i in range(5):
        opp = Opportunity(
            type="vacancy",
            title=f"Вакансия {i}",
            description=f"Тестовая вакансия {i}",
            requirements="Python",
            responsibilities="Разработка",
            status=OpportunityStatus.ACTIVE,
            is_moderated=True,
            work_format="remote",
            experience_level="middle",
            employment_type="full_time",
            city="Москва",
            company_id=test_company.id,
        )
        db_session.add(opp)
        opportunities.append(opp)
    await db_session.commit()

    # Создаём несколько откликов на разные вакансии
    applicant_profile_id = test_applicant.profile.id
    for opp in opportunities:
        app = Application(
            opportunity_id=opp.id,
            applicant_id=applicant_profile_id,
            status=ApplicationStatus.PENDING,
            cover_letter=f"Отклик на {opp.title}",
        )
        db_session.add(app)
    await db_session.commit()

    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    # Первая страница
    resp = await client.get("/api/v1/applications/me?limit=2&offset=0", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    # Вторая страница
    resp2 = await client.get("/api/v1/applications/me?limit=2&offset=2", headers=headers)
    assert resp2.status_code == status.HTTP_200_OK
    data2 = resp2.json()
    assert len(data2["items"]) == 2
    assert data2["offset"] == 2


@pytest.mark.asyncio
async def test_get_my_applications_unauthorized(
    client: AsyncClient,
) -> None:
    """Попытка получить список откликов без авторизации."""
    resp = await client.get("/api/v1/applications/me")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ═════════════════════════════════════════════════════════════
#  БЛОК 3: GET /applications/me/{id} (Детали отклика соискателя)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_my_application_detail_success(
    client: AsyncClient,
    test_applicant: User,
    test_opportunity: Opportunity,
    test_application: Application,
) -> None:
    """Успешное получение деталей своего отклика."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/applications/me/{test_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["id"] == str(test_application.id)
    assert data["status"] == "pending"
    assert data["cover_letter"] == test_application.cover_letter
    assert "opportunity" in data
    assert data["opportunity"]["title"] == test_opportunity.title


@pytest.mark.asyncio
async def test_get_my_application_detail_not_found(
    client: AsyncClient,
    test_applicant: User,
) -> None:
    """Попытка получить несуществующий отклик."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    import uuid

    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/applications/me/{fake_id}", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND

    data = resp.json()
    assert data["error"]["code"] == "APPLICATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_my_application_detail_not_owner(
    client: AsyncClient,
    test_applicant: User,
    test_application: Application,
    db_session: AsyncSession,
) -> None:
    """Попытка получить чужой отклик."""
    # Создаём другого соискателя
    other_applicant = User(
        email="other_applicant@test.ru",
        hashed_password=hash_password("test_password"),
        role="applicant",
        is_active=True,
        profile=Profile(first_name="Другой", last_name="Соискатель"),
    )
    db_session.add(other_applicant)
    await db_session.commit()

    # Reload with profile
    result = await db_session.execute(select(User).options(selectinload(User.profile)).where(User.id == other_applicant.id))
    other_applicant = result.scalar_one()

    token = await _login_user(client, other_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/applications/me/{test_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    data = resp.json()
    assert data["error"]["code"] == "PERMISSION_DENIED"


# ═════════════════════════════════════════════════════════════
#  БЛОК 4: DELETE /applications/me/{id} (Отозвать отклик)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_withdraw_application_success(
    client: AsyncClient,
    test_applicant: User,
    test_application: Application,
) -> None:
    """Успешный отзыв отклика со статусом PENDING."""
    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(f"/api/v1/applications/me/{test_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["status"] == "withdrawn"
    assert len(data["status_history"]) >= 1  # История содержит как минимум запись о withdrawal


@pytest.mark.asyncio
async def test_withdraw_application_viewed_status(
    client: AsyncClient,
    test_applicant: User,
    test_application: Application,
    db_session: AsyncSession,
) -> None:
    """Отзыв отклика со статусом VIEWED."""
    test_application.status = ApplicationStatus.VIEWED
    await db_session.commit()

    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(f"/api/v1/applications/me/{test_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_withdraw_application_not_allowed_accepted(
    client: AsyncClient,
    test_applicant: User,
    test_application: Application,
    db_session: AsyncSession,
) -> None:
    """Попытка отозвать отклик со статусом ACCEPTED."""
    test_application.status = ApplicationStatus.ACCEPTED
    await db_session.commit()

    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(f"/api/v1/applications/me/{test_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    data = resp.json()
    assert data["error"]["code"] == "APPLICATION_WITHDRAW_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_withdraw_application_not_allowed_rejected(
    client: AsyncClient,
    test_applicant: User,
    test_application: Application,
    db_session: AsyncSession,
) -> None:
    """Попытка отозвать отклик со статусом REJECTED."""
    test_application.status = ApplicationStatus.REJECTED
    await db_session.commit()

    token = await _login_user(client, test_applicant.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.delete(f"/api/v1/applications/me/{test_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    data = resp.json()
    assert data["error"]["code"] == "APPLICATION_WITHDRAW_NOT_ALLOWED"


# ═════════════════════════════════════════════════════════════
#  БЛОК 5: GET /opportunities/{id}/applications (Список для работодателя)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_opportunity_applications_success(
    client: AsyncClient,
    test_employer: User,
    test_company: Company,
    test_opportunity: Opportunity,
    test_application: Application,
) -> None:
    """Успешное получение списка откликов на вакансию работодателя."""
    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"/api/v1/opportunities/{test_opportunity.id}/applications",
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["id"] == str(test_application.id)
    assert "applicant_profile" in item


@pytest.mark.asyncio
async def test_get_opportunity_applications_not_owner(
    client: AsyncClient,
    test_employer: User,
    test_company: Company,
    db_session: AsyncSession,
) -> None:
    """Попытка получить отклики на чужую вакансию."""
    # Создаём другую компанию и вакансию
    other_employer = User(
        email="other_employer@test.ru",
        hashed_password=hash_password("test_password"),
        role="employer",
        is_active=True,
        profile=Profile(first_name="Другой", last_name="Работодатель"),
    )
    db_session.add(other_employer)
    await db_session.flush()

    other_company = Company(
        owner_id=other_employer.id,
        name="Другая компания",
        inn="1111111111",
        city="Москва",
        verification_status=VerificationStatus.APPROVED,
        is_active=True,
    )
    db_session.add(other_company)
    await db_session.flush()

    other_opportunity = Opportunity(
        type="vacancy",
        title="Чужая вакансия",
        status=OpportunityStatus.ACTIVE,
        is_moderated=True,
        work_format="remote",
        city="Москва",
        company_id=other_company.id,
    )
    db_session.add(other_opportunity)
    await db_session.commit()

    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"/api/v1/opportunities/{other_opportunity.id}/applications",
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_opportunity_applications_unauthorized(
    client: AsyncClient,
    test_opportunity: Opportunity,
) -> None:
    """Попытка получить отклики без авторизации."""
    resp = await client.get(f"/api/v1/opportunities/{test_opportunity.id}/applications")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ═════════════════════════════════════════════════════════════
#  БЛОК 6: GET /applications/{id} (Детали для работодателя)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_employer_application_detail_success(
    client: AsyncClient,
    test_employer: User,
    test_company: Company,
    test_opportunity: Opportunity,
    test_application: Application,
) -> None:
    """Успешное получение деталей отклика работодателем."""
    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/applications/{test_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["id"] == str(test_application.id)
    assert data["applicant_id"] == str(test_application.applicant_id)
    assert "applicant_profile" in data
    assert "opportunity" in data


@pytest.mark.asyncio
async def test_get_employer_application_detail_not_owner(
    client: AsyncClient,
    test_employer: User,
    db_session: AsyncSession,
) -> None:
    """Попытка получить детали чужого отклика."""
    # Создаём чужую вакансию и отклик
    other_employer = User(
        email="other_employer2@test.ru",
        hashed_password=hash_password("test_password"),
        role="employer",
        is_active=True,
        profile=Profile(first_name="Другой2", last_name="Работодатель"),
    )
    db_session.add(other_employer)
    await db_session.flush()

    other_company = Company(
        owner_id=other_employer.id,
        name="Другая компания 2",
        inn="2222222222",
        city="Москва",
        verification_status=VerificationStatus.APPROVED,
        is_active=True,
    )
    db_session.add(other_company)
    await db_session.flush()

    other_opportunity = Opportunity(
        type="vacancy",
        title="Чужая вакансия 2",
        status=OpportunityStatus.ACTIVE,
        is_moderated=True,
        work_format="remote",
        city="Москва",
        company_id=other_company.id,
    )
    db_session.add(other_opportunity)
    await db_session.flush()

    applicant = User(
        email="applicant2@test.ru",
        hashed_password=hash_password("test_password"),
        role="applicant",
        is_active=True,
        profile=Profile(first_name="Другой", last_name="Соискатель2"),
    )
    db_session.add(applicant)
    await db_session.flush()

    # Reload applicant with profile
    result = await db_session.execute(select(User).options(selectinload(User.profile)).where(User.id == applicant.id))
    applicant = result.scalar_one()

    other_application = Application(
        opportunity_id=other_opportunity.id,
        applicant_id=applicant.profile.id,
        status=ApplicationStatus.PENDING,
    )
    db_session.add(other_application)
    await db_session.commit()

    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/applications/{other_application.id}", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


# ═════════════════════════════════════════════════════════════
#  БЛОК 7: PATCH /applications/{id}/status (Смена статуса)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_application_status_pending_to_viewed(
    client: AsyncClient,
    test_employer: User,
    test_application: Application,
) -> None:
    """Успешная смена статуса с PENDING на VIEWED."""
    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    status_data = {
        "status": "viewed",
    }

    resp = await client.patch(
        f"/api/v1/applications/{test_application.id}/status",
        json=status_data,
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["status"] == "viewed"
    assert data["viewed_at"] is not None


@pytest.mark.asyncio
async def test_update_application_status_with_comment(
    client: AsyncClient,
    test_employer: User,
    test_application: Application,
) -> None:
    """Смена статуса с комментарием."""
    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    status_data = {
        "status": "accepted",
        "employer_comment": "Отличное резюме! Приглашаем на собеседование.",
    }

    resp = await client.patch(
        f"/api/v1/applications/{test_application.id}/status",
        json=status_data,
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["status"] == "accepted"
    assert data["employer_comment"] == status_data["employer_comment"]


@pytest.mark.asyncio
async def test_update_application_status_invalid_transition(
    client: AsyncClient,
    test_employer: User,
    test_application: Application,
    db_session: AsyncSession,
) -> None:
    """Попытка недопустимого перехода статуса."""
    # Устанавливаем статус ACCEPTED
    test_application.status = ApplicationStatus.ACCEPTED
    await db_session.commit()

    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    # Пытаемся вернуть в PENDING
    status_data = {
        "status": "pending",
    }

    resp = await client.patch(
        f"/api/v1/applications/{test_application.id}/status",
        json=status_data,
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    data = resp.json()
    assert data["error"]["code"] == "INVALID_STATUS_TRANSITION"


@pytest.mark.asyncio
async def test_update_application_status_withdrawn_by_employer(
    client: AsyncClient,
    test_employer: User,
    test_application: Application,
) -> None:
    """Попытка работодателя установить статус WITHDRAWN."""
    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    status_data = {
        "status": "withdrawn",
    }

    resp = await client.patch(
        f"/api/v1/applications/{test_application.id}/status",
        json=status_data,
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    data = resp.json()
    assert data["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ═════════════════════════════════════════════════════════════
#  БЛОК 8: PATCH /applications/{id}/feedback (Обратная связь)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_application_feedback_success(
    client: AsyncClient,
    test_employer: User,
    test_application: Application,
) -> None:
    """Успешное обновление обратной связи."""
    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    feedback_data = {
        "employer_comment": "Кандидат прошёл собеседование.",
        "employer_note": "Внутренняя заметка: зарплата 200к.",
    }

    resp = await client.patch(
        f"/api/v1/applications/{test_application.id}/feedback",
        json=feedback_data,
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["employer_comment"] == feedback_data["employer_comment"]
    assert data["employer_note"] == feedback_data["employer_note"]


@pytest.mark.asyncio
async def test_update_application_feedback_partial(
    client: AsyncClient,
    test_employer: User,
    test_application: Application,
) -> None:
    """Обновление только комментария."""
    token = await _login_user(client, test_employer.email, "test_password")
    headers = {"Authorization": f"Bearer {token}"}

    feedback_data = {
        "employer_comment": "Только комментарий.",
    }

    resp = await client.patch(
        f"/api/v1/applications/{test_application.id}/feedback",
        json=feedback_data,
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["employer_comment"] == feedback_data["employer_comment"]
    assert data["employer_note"] is None


@pytest.mark.asyncio
async def test_update_application_feedback_unauthorized(
    client: AsyncClient,
    test_application: Application,
) -> None:
    """Попытка обновить обратную связь без авторизации."""
    feedback_data = {
        "employer_comment": "Комментарий",
    }

    resp = await client.patch(
        f"/api/v1/applications/{test_application.id}/feedback",
        json=feedback_data,
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
