"""
Интеграционные тесты публичных эндпоинтов возможностей.

Тестируются эндпоинты:
  - GET /api/v1/opportunities          → список карточек
  - GET /api/v1/opportunities/map      → маркеры для карты
  - GET /api/v1/opportunities/filters  → фильтры для поиска
  - GET /api/v1/opportunities/{id}     → детальная информация

Стратегия:
  - Используем тестовую БД из conftest
  - Создаём тестовые данные (компании, возможности) через SQLAlchemy
  - Проверяем фильтрацию, пагинацию, определение города по IP
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import status
from geoalchemy2.shape import from_shape
from httpx import AsyncClient
from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.company import Company
from src.models.enums import SkillCategory
from src.models.opportunity import Opportunity, OpportunitySkill, OpportunityTag, Tag
from src.models.skill import Skill


@pytest_asyncio.fixture
async def test_companies(db_session: AsyncSession) -> dict[str, Company]:
    """Создаёт тестовые компании для всех тестов."""
    from src.models.user import Profile, User

    owners = {
        "sber": User(
            email="sber_company@test.ru",
            hashed_password="test_password_hash",
            role="employer",
            is_active=True,
            profile=Profile(first_name="Sber", last_name="Company"),
        ),
        "yandex": User(
            email="yandex_company@test.ru",
            hashed_password="test_password_hash",
            role="employer",
            is_active=True,
            profile=Profile(first_name="Yandex", last_name="Company"),
        ),
        "tinkoff": User(
            email="tinkoff_company@test.ru",
            hashed_password="test_password_hash",
            role="employer",
            is_active=True,
            profile=Profile(first_name="Tinkoff", last_name="Company"),
        ),
        "inactive": User(
            email="inactive_company@test.ru",
            hashed_password="test_password_hash",
            role="employer",
            is_active=True,
            profile=Profile(first_name="Inactive", last_name="Company"),
        ),
    }
    db_session.add_all(owners.values())
    await db_session.flush()  # Получаем ID

    companies = {
        "sber": Company(
            owner_id=owners["sber"].id,
            name="ПАО Сбербанк",
            inn="7707083893",
            corporate_email="hr@sberbank.ru",
            website_url="https://sberbank.ru",
            city="Москва",
            is_active=True,
            verification_status="approved",
        ),
        "yandex": Company(
            owner_id=owners["yandex"].id,
            name="Яндекс",
            inn="773601001",
            corporate_email="hr@yandex.ru",
            website_url="https://yandex.ru",
            city="Москва",
            is_active=True,
            verification_status="approved",
        ),
        "tinkoff": Company(
            owner_id=owners["tinkoff"].id,
            name="Тинькофф",
            inn="7728168971",
            corporate_email="hr@tinkoff.ru",
            website_url="https://tinkoff.ru",
            city="Санкт-Петербург",
            is_active=True,
            verification_status="approved",
        ),
        "inactive": Company(
            owner_id=owners["inactive"].id,
            name="Неактивная компания",
            inn="0000000001",
            corporate_email="test@test.ru",
            city="Москва",
            is_active=False,  # неактивная
            verification_status="pending",
        ),
    }
    db_session.add_all(companies.values())
    await db_session.commit()
    return companies


@pytest_asyncio.fixture
async def test_tags(db_session: AsyncSession) -> dict[str, Tag]:
    """Создаёт тестовые теги."""
    tags = {
        "it": Tag(name="IT", slug="it"),
        "finance": Tag(name="Финансы", slug="finances"),
        "python": Tag(name="Python", slug="python"),
        "junior": Tag(name="Junior", slug="junior"),
    }
    db_session.add_all(tags.values())
    await db_session.commit()
    return tags


@pytest_asyncio.fixture
async def test_skills(db_session: AsyncSession) -> dict[str, Skill]:
    """Создаёт тестовые навыки."""
    skills = {
        "python": Skill(
            name="Python",
            slug="python",
            category=SkillCategory.LANGUAGE,
        ),
        "fastapi": Skill(
            name="FastAPI",
            slug="fastapi",
            category=SkillCategory.FRAMEWORK,
        ),
        "sqlalchemy": Skill(
            name="SQLAlchemy",
            slug="sqlalchemy",
            category=SkillCategory.DATABASE,
        ),
        "docker": Skill(
            name="Docker",
            slug="docker",
            category=SkillCategory.DEVOPS,
        ),
    }
    db_session.add_all(skills.values())
    await db_session.commit()
    return skills


@pytest_asyncio.fixture
async def test_opportunities(
    db_session: AsyncSession,
    test_companies: dict[str, Company],
    test_tags: dict[str, Tag],
    test_skills: dict[str, Skill],
) -> dict[str, Opportunity]:
    """Создаёт тестовые возможности разных типов."""
    now = datetime.utcnow()
    opps = {
        # Вакансия Москва, офис
        "vacancy_moscow_office": Opportunity(
            type="vacancy",
            title="Python Backend Разработчик",
            description="Разработка backend для банковских систем",
            requirements="Python 3.11+, FastAPI, PostgreSQL",
            responsibilities="Разработка новых фич, код-ревью",
            status="active",
            is_moderated=True,
            work_format="office",
            experience_level="middle",
            employment_type="full_time",
            salary_min=150000,
            salary_max=250000,
            salary_currency="RUB",
            salary_gross=True,
            city="Москва",
            address="ул. Вавилова, д 19",
            location=from_shape(Point(37.6176, 55.7558)),  # Москва
            published_at=now,
            expires_at=now + timedelta(days=30),
            views_count=100,
            applications_count=15,
            company_id=test_companies["sber"].id,
        ),
        # Вакансия Москва, гибрид
        "vacancy_moscow_hybrid": Opportunity(
            type="vacancy",
            title="Senior Python Developer",
            description="Разработка высоконагруженных систем",
            status="active",
            is_moderated=True,
            work_format="hybrid",
            experience_level="senior",
            employment_type="full_time",
            salary_min=300000,
            salary_max=500000,
            salary_currency="RUB",
            salary_gross=True,
            city="Москва",
            location=from_shape(Point(37.6200, 55.7520)),
            published_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29),
            company_id=test_companies["yandex"].id,
        ),
        # Вакансия СПб, удалёнка
        "vacancy_spb_remote": Opportunity(
            type="vacancy",
            title="Python Разработчик (Remote)",
            description="Удалённая разработка",
            status="active",
            is_moderated=True,
            work_format="remote",
            experience_level="junior",
            employment_type="full_time",
            salary_min=80000,
            salary_max=120000,
            city="Санкт-Петербург",
            location=from_shape(Point(30.3158, 59.9392)),  # СПб
            published_at=now - timedelta(days=2),
            company_id=test_companies["tinkoff"].id,
        ),
        # Стажировка
        "internship_moscow": Opportunity(
            type="internship",
            title="Стажёр Python Разработчик",
            description="Стажировка с возможностью трудоустройства",
            status="active",
            is_moderated=True,
            work_format="office",
            experience_level="intern",
            employment_type="part_time",
            salary_min=30000,
            salary_max=50000,
            city="Москва",
            location=from_shape(Point(37.6150, 55.7500)),
            published_at=now,
            max_participants=5,
            current_participants=2,
            company_id=test_companies["sber"].id,
        ),
        # Мероприятие
        "event_moscow": Opportunity(
            type="event",
            title="Python Conference 2026",
            description="Ежегодная конференция по Python",
            status="active",
            is_moderated=True,
            work_format="office",
            city="Москва",
            location=from_shape(Point(37.6100, 55.7480)),
            published_at=now - timedelta(days=5),
            event_start_at=now + timedelta(days=60),
            event_end_at=now + timedelta(days=61),
            max_participants=500,
            current_participants=150,
            company_id=test_companies["yandex"].id,
        ),
        # Неактивная вакансия (не должна попадать в публичный список)
        "inactive_vacancy": Opportunity(
            type="vacancy",
            title="Скрытая вакансия",
            status="draft",  # не active
            is_moderated=False,
            work_format="office",
            city="Москва",
            company_id=test_companies["inactive"].id,
        ),
        # Вакансия без координат (для теста карты)
        "vacancy_no_location": Opportunity(
            type="vacancy",
            title="Вакансия без координат",
            status="active",
            is_moderated=True,
            work_format="remote",
            experience_level="middle",
            salary_min=100000,
            salary_max=150000,
            city="Казань",
            location=None,  # нет координат
            company_id=test_companies["tinkoff"].id,
        ),
    }

    # Добавляем теги и навыки
    for opp_key, opp in opps.items():
        if opp_key in ["vacancy_moscow_office", "vacancy_moscow_hybrid"]:
            opp.opportunity_tags.append(OpportunityTag(opportunity=opp, tag=test_tags["python"]))
            opp.opportunity_skills.append(OpportunitySkill(opportunity=opp, skill=test_skills["python"]))
            opp.opportunity_skills.append(OpportunitySkill(opportunity=opp, skill=test_skills["fastapi"]))

    db_session.add_all(opps.values())
    await db_session.commit()
    return opps


# ═════════════════════════════════════════════════════════════
#  БЛОК 1: GET /api/v1/opportunities (список)
# ═════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_opportunities_default_params(
    client: AsyncClient,
    test_opportunities: dict[str, Opportunity],
) -> None:
    """
    Базовый запрос без параметров.
    Возвращает только активные промодерированные возможности.
    """
    resp = await client.get("/api/v1/opportunities")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["total"] == 4
    assert len(data["items"]) == 4

    for item in data["items"]:
        assert "id" in item
        assert "type" in item
        assert "title" in item
        assert "status" in item
        assert "work_format" in item
        assert "company" in item
        assert "location" in item
        assert "salary" in item

        assert "id" in item["company"]
        assert "name" in item["company"]
        assert "city" in item["company"]

        assert "city" in item["location"]

        assert "currency" in item["salary"]

    types = {item["type"] for item in data["items"]}
    assert "vacancy" in types
    assert "internship" in types
    assert "event" in types

    company_names = {item["company"]["name"] for item in data["items"]}
    assert "ПАО Сбербанк" in company_names
    assert "Яндекс" in company_names
    titles = {item["title"] for item in data["items"]}
    assert "Скрытая вакансия" not in titles


@pytest.mark.asyncio
async def test_get_opportunities_filter_by_type(
    client: AsyncClient,
    test_opportunities: dict[str, Opportunity],
) -> None:
    """Фильтрация по типу: только вакансии."""
    resp = await client.get("/api/v1/opportunities?type=vacancy")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["total"] == 2
    assert all(item["type"] == "vacancy" for item in data["items"])


@pytest.mark.asyncio
async def test_get_opportunities_filter_by_multiple_types(
    client: AsyncClient,
    test_opportunities: dict[str, Opportunity],
) -> None:
    """Фильтрация по нескольким типам через запятую."""
    resp = await client.get("/api/v1/opportunities?type=vacancy,internship")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["total"] == 3
    types = {item["type"] for item in data["items"]}
    assert types == {"vacancy", "internship"}


@pytest.mark.asyncio
async def test_get_opportunities_filter_by_city(
    client: AsyncClient,
    test_opportunities: dict[str, Opportunity],
) -> None:
    """Фильтрация по городу."""
    resp = await client.get("/api/v1/opportunities?city=Москва")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["total"] == 4  # 4 в Москве
    assert all(item["location"]["city"] == "Москва" for item in data["items"])


# @pytest.mark.asyncio
# async def test_get_opportunities_filter_by_work_format(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Фильтрация по формату работы."""
#     resp = await client.get("/api/v1/opportunities?work_format=remote")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert data["total"] >= 1
#     assert all(item["work_format"] == "remote" for item in data["items"])


# @pytest.mark.asyncio
# async def test_get_opportunities_filter_by_experience_level(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Фильтрация по уровню опыта."""
#     resp = await client.get("/api/v1/opportunities?experience_level=senior")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert data["total"] >= 1
#     assert all(
#         item["experience_level"] == "senior" for item in data["items"]
#         if item["experience_level"] is not None
#     )


# @pytest.mark.asyncio
# async def test_get_opportunities_filter_by_salary_range(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Фильтрация по зарплате."""
#     # Минимум 200k
#     resp = await client.get("/api/v1/opportunities?salary_min=200000")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # Должны попасть вакансии с max >= 200k
#     assert data["total"] >= 1
#     for item in data["items"]:
#         salary_max = item["salary"]["max"]
#         salary_min = item["salary"]["min"]
#         assert salary_max is None or salary_max >= 200000 or salary_min >= 200000


# @pytest.mark.asyncio
# async def test_get_opportunities_pagination(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Тест пагинации: limit/offset."""
#     # Первая страница
#     resp1 = await client.get("/api/v1/opportunities?limit=2&offset=0")
#     assert resp1.status_code == status.HTTP_200_OK
#     data1 = resp1.json()
#     assert len(data1["items"]) == 2
#     assert data1["total"] == 6
#     assert data1["limit"] == 2
#     assert data1["offset"] == 0

#     # Вторая страница
#     resp2 = await client.get("/api/v1/opportunities?limit=2&offset=2")
#     assert resp2.status_code == status.HTTP_200_OK
#     data2 = resp2.json()
#     assert len(data2["items"]) == 2
#     assert data2["offset"] == 2

#     # IDs не должны пересекаться
#     ids1 = {item["id"] for item in data1["items"]}
#     ids2 = {item["id"] for item in data2["items"]}
#     assert ids1.isdisjoint(ids2)


# @pytest.mark.asyncio
# async def test_get_opportunities_limit_max(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка ограничения limit <= 200."""
#     resp = await client.get("/api/v1/opportunities?limit=200")
#     assert resp.status_code == status.HTTP_200_OK

#     # Превышение лимита
#     resp_invalid = await client.get("/api/v1/opportunities?limit=201")
#     assert resp_invalid.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# @pytest.mark.asyncio
# async def test_get_opportunities_combined_filters(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Комбинированная фильтрация: город + тип + формат."""
#     resp = await client.get(
#         "/api/v1/opportunities?city=Москва&type=vacancy&work_format=office,hybrid"
#     )
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # Только вакансии в Москве с офисом/гибридом
#     for item in data["items"]:
#         assert item["location"]["city"] == "Москва"
#         assert item["type"] == "vacancy"
#         assert item["work_format"] in ["office", "hybrid"]


# @pytest.mark.asyncio
# async def test_get_opportunities_detected_city_from_ip(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка что возвращается detected_city."""
#     resp = await client.get("/api/v1/opportunities")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # detected_city должен быть в ответе
#     assert "detected_city" in data
#     assert "detected_from_ip" in data
#     assert isinstance(data["detected_from_ip"], bool)


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 2: GET /api/v1/opportunities/map (маркеры)
# # ═════════════════════════════════════════════════════════════


# @pytest.mark.asyncio
# async def test_get_map_markers_empty_db(client: AsyncClient) -> None:
#     """Пустая БД → пустой список маркеров."""
#     resp = await client.get("/api/v1/opportunities/map")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()
#     assert data["markers"] == []
#     assert data["total"] == 0


# @pytest.mark.asyncio
# async def test_get_map_markers_excludes_no_location(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Маркеры не включают возможности без координат."""
#     resp = await client.get("/api/v1/opportunities/map")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # vacancy_no_location не должна попасть
#     ids = [m["id"] for m in data["markers"]]
#     assert str(test_opportunities["vacancy_no_location"].id) not in ids

#     # Все маркеры должны иметь координаты
#     for marker in data["markers"]:
#         assert "lat" in marker
#         assert "lng" in marker
#         assert marker["lat"] is not None
#         assert marker["lng"] is not None


# @pytest.mark.asyncio
# async def test_get_map_markers_structure(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка структуры маркера."""
#     resp = await client.get("/api/v1/opportunities/map")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert len(data["markers"]) > 0
#     marker = data["markers"][0]

#     # Обязательные поля
#     assert "id" in marker
#     assert "type" in marker
#     assert "lat" in marker
#     assert "lng" in marker
#     assert "title" in marker
#     assert "company_name" in marker
#     assert "work_format" in marker

#     # Опциональные
#     assert "salary_min" in marker
#     assert "salary_max" in marker
#     assert "company_logo_url" in marker
#     assert "city" in marker


# @pytest.mark.asyncio
# async def test_get_map_markers_filter_by_city(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Фильтрация маркеров по городу."""
#     resp = await client.get("/api/v1/opportunities/map?city=Москва")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # Только Москва
#     assert all(m["city"] == "Москва" for m in data["markers"])


# @pytest.mark.asyncio
# async def test_get_map_markers_bounding_box(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Фильтрация по bounding box карты."""
#     # Bounding box для Москвы (примерно)
#     resp = await client.get(
#         "/api/v1/opportunities/map?"
#         "sw_lat=55.70&sw_lng=37.50&ne_lat=55.80&ne_lng=37.70"
#     )
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # Должны попасть только маркеры в пределах box
#     for marker in data["markers"]:
#         assert 55.70 <= marker["lat"] <= 55.80
#         assert 37.50 <= marker["lng"] <= 37.70


# @pytest.mark.asyncio
# async def test_get_map_markers_bounding_box_excludes_spb(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Bounding box исключает СПб когда смотрим на Москву."""
#     # Москва бокс
#     resp = await client.get(
#         "/api/v1/opportunities/map?"
#         "sw_lat=55.70&sw_lng=37.50&ne_lat=55.80&ne_lng=37.70"
#     )
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # СПб маркер (30.3158, 59.9392) не должен попасть
#     spb_id = str(test_opportunities["vacancy_spb_remote"].id)
#     ids = [m["id"] for m in data["markers"]]
#     assert spb_id not in ids


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 3: GET /api/v1/opportunities/filters (фильтры)
# # ═════════════════════════════════════════════════════════════


# @pytest.mark.asyncio
# async def test_get_filters_structure(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка структуры ответа фильтров."""
#     resp = await client.get("/api/v1/opportunities/filters")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert "cities" in data
#     assert "types" in data
#     assert "work_formats" in data
#     assert "experience_levels" in data
#     assert "employment_types" in data
#     assert "salary_ranges" in data


# @pytest.mark.asyncio
# async def test_get_filters_cities(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка городов в фильтрах."""
#     resp = await client.get("/api/v1/opportunities/filters")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     cities = data["cities"]
#     assert len(cities) > 0

#     # Москва должна быть
#     moscow = next((c for c in cities if c["name"] == "Москва"), None)
#     assert moscow is not None
#     assert "count" in moscow
#     assert moscow["count"] > 0

#     # СПб должен быть
#     spb = next((c for c in cities if c["name"] == "Санкт-Петербург"), None)
#     assert spb is not None


# @pytest.mark.asyncio
# async def test_get_filters_types(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка типов в фильтрах."""
#     resp = await client.get("/api/v1/opportunities/filters")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     types = data["types"]
#     type_values = [t["value"] for t in types]

#     # Все типы должны быть представлены
#     assert "vacancy" in type_values
#     assert "internship" in type_values
#     assert "event" in type_values


# @pytest.mark.asyncio
# async def test_get_filters_work_formats(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка форматов работы."""
#     resp = await client.get("/api/v1/opportunities/filters")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     work_formats = data["work_formats"]
#     format_values = [f["value"] for f in work_formats]

#     assert "office" in format_values
#     assert "hybrid" in format_values
#     assert "remote" in format_values


# @pytest.mark.asyncio
# async def test_get_filters_with_city_filter(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Фильтры с учётом города."""
#     resp = await client.get("/api/v1/opportunities/filters?city=Москва")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # Для Москвы должны быть свои count
#     cities = data["cities"]
#     # При фильтре по Москве должна быть только Москва или Москва на первом месте
#     if len(cities) > 1:
#         assert cities[0]["name"] == "Москва"


# @pytest.mark.asyncio
# async def test_get_filters_detected_city(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка detected_city в фильтрах."""
#     resp = await client.get("/api/v1/opportunities/filters")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert "detected_city" in data


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 4: GET /api/v1/opportunities/{id} (детальная карточка)
# # ═════════════════════════════════════════════════════════════


# @pytest.mark.asyncio
# async def test_get_opportunity_detail_success(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Успешный запрос детальной информации."""
#     opp_id = test_opportunities["vacancy_moscow_office"].id
#     resp = await client.get(f"/api/v1/opportunities/{opp_id}")

#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     # Основные поля
#     assert data["id"] == str(opp_id)
#     assert data["type"] == "vacancy"
#     assert data["title"] == "Python Backend Разработчик"
#     assert data["status"] == "active"
#     assert data["description"] is not None
#     assert data["work_format"] == "office"
#     assert data["experience_level"] == "middle"

#     # Компания
#     assert "company" in data
#     assert data["company"]["name"] == "ПАО Сбербанк"
#     assert "id" in data["company"]
#     assert "logo_url" in data["company"]

#     # Локация
#     assert "location" in data
#     assert data["location"]["city"] == "Москва"
#     assert data["location"]["address"] == "ул. Вавилова, д 19"

#     # Зарплата
#     assert "salary" in data
#     assert data["salary"]["min"] == 150000
#     assert data["salary"]["max"] == 250000
#     assert data["salary"]["currency"] == "RUB"

#     # Счётчики
#     assert data["views_count"] >= 0
#     assert data["applications_count"] >= 0

#     # Для гостей is_favorited/is_applied = False
#     assert data["is_favorited"] is False
#     assert data["is_applied"] is False


# @pytest.mark.asyncio
# async def test_get_opportunity_detail_with_skills_tags(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка что навыки и теги возвращаются."""
#     opp_id = test_opportunities["vacancy_moscow_office"].id
#     resp = await client.get(f"/api/v1/opportunities/{opp_id}")

#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert "skills" in data
#     assert "tags" in data

#     # Навыки должны быть (Python, FastAPI)
#     assert len(data["skills"]) > 0
#     skill_names = [s["name"] for s in data["skills"]]
#     assert "Python" in skill_names

#     # Теги должны быть
#     assert len(data["tags"]) > 0


# @pytest.mark.asyncio
# async def test_get_opportunity_detail_internship(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Детальная информация о стажировке."""
#     opp_id = test_opportunities["internship_moscow"].id
#     resp = await client.get(f"/api/v1/opportunities/{opp_id}")

#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert data["type"] == "internship"
#     assert data["max_participants"] == 5
#     assert data["current_participants"] == 2


# @pytest.mark.asyncio
# async def test_get_opportunity_detail_event(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Детальная информация о мероприятии."""
#     opp_id = test_opportunities["event_moscow"].id
#     resp = await client.get(f"/api/v1/opportunities/{opp_id}")

#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     assert data["type"] == "event"
#     assert "event_start_at" in data
#     assert "event_end_at" in data
#     assert data["max_participants"] == 500
#     assert data["current_participants"] == 150


# @pytest.mark.asyncio
# async def test_get_opportunity_detail_not_found(
#     client: AsyncClient,
# ) -> None:
#     """Запрос несуществующей вакансии."""
#     fake_id = uuid.uuid4()
#     resp = await client.get(f"/api/v1/opportunities/{fake_id}")

#     assert resp.status_code == status.HTTP_404_NOT_FOUND


# @pytest.mark.asyncio
# async def test_get_opportunity_detail_inactive(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Запрос неактивной вакансии (должна вернуться или 404)."""
#     opp_id = test_opportunities["inactive_vacancy"].id
#     resp = await client.get(f"/api/v1/opportunities/{opp_id}")

#     # Неактивная вакансия может возвращать 404 или данные без чувствительной инфы
#     # Зависит от бизнес-логики — здесь проверяем что не падает 500
#     assert resp.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR


# @pytest.mark.asyncio
# async def test_get_opportunity_detail_invalid_uuid(
#     client: AsyncClient,
# ) -> None:
#     """Невалидный UUID → 404 (FastAPI не может спарсить путь)."""
#     resp = await client.get("/api/v1/opportunities/not-a-uuid")

#     assert resp.status_code == status.HTTP_404_NOT_FOUND


# # ═════════════════════════════════════════════════════════════
# #  БЛОК 5: Комплексные тесты
# # ═════════════════════════════════════════════════════════════


# @pytest.mark.asyncio
# async def test_opportunities_api_full_flow(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """
#     Полный сценарий использования API:
#     1. Получаем фильтры
#     2. Получаем список по фильтру
#     3. Получаем детальную информацию
#     4. Получаем маркеры на карте
#     """
#     # 1. Фильтры
#     filters_resp = await client.get("/api/v1/opportunities/filters")
#     assert filters_resp.status_code == status.HTTP_200_OK
#     filters = filters_resp.json()
#     assert len(filters["cities"]) > 0

#     # 2. Список (фильтр по Москве)
#     list_resp = await client.get("/api/v1/opportunities?city=Москва&limit=10")
#     assert list_resp.status_code == status.HTTP_200_OK
#     list_data = list_resp.json()
#     assert list_data["total"] > 0

#     if list_data["items"]:
#         # 3. Детальная информация первой вакансии
#         first_item = list_data["items"][0]
#         detail_resp = await client.get(f"/api/v1/opportunities/{first_item['id']}")
#         assert detail_resp.status_code == status.HTTP_200_OK
#         detail_data = detail_resp.json()
#         assert detail_data["id"] == first_item["id"]

#     # 4. Маркеры на карте
#     map_resp = await client.get("/api/v1/opportunities/map?city=Москва")
#     assert map_resp.status_code == status.HTTP_200_OK
#     map_data = map_resp.json()
#     assert len(map_data["markers"]) > 0


# @pytest.mark.asyncio
# async def test_opportunities_pagination_edge_cases(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Тест граничных значений пагинации."""
#     # offset больше total
#     resp = await client.get("/api/v1/opportunities?offset=1000")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()
#     assert data["items"] == []
#     assert data["total"] == 6

#     # limit=1
#     resp = await client.get("/api/v1/opportunities?limit=1")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()
#     assert len(data["items"]) == 1

#     # offset=0, limit=1 (первая запись)
#     resp_first = await client.get("/api/v1/opportunities?limit=1&offset=0")
#     first_id = resp_first.json()["items"][0]["id"]

#     # offset=1, limit=1 (вторая запись)
#     resp_second = await client.get("/api/v1/opportunities?limit=1&offset=1")
#     second_id = resp_second.json()["items"][0]["id"]

#     assert first_id != second_id


# @pytest.mark.asyncio
# async def test_opportunities_search_preserves_ordering(
#     client: AsyncClient,
#     test_opportunities: dict[str, Opportunity],
# ) -> None:
#     """Проверка что результаты сортируются по published_at (новые первыми)."""
#     resp = await client.get("/api/v1/opportunities?limit=10")
#     assert resp.status_code == status.HTTP_200_OK
#     data = resp.json()

#     if len(data["items"]) > 1:
#         dates = [
#             datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
#             for item in data["items"]
#             if item["published_at"] is not None
#         ]
#         # Должно быть по убыванию
#         assert dates == sorted(dates, reverse=True)
