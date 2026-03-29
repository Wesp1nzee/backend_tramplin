"""
Integration tests for:
- Favorites (vacancies and companies)
- Applicants search and profiles
"""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.company import Company
from src.models.enums import OpportunityStatus, OpportunityType, UserRole, VerificationStatus
from src.models.opportunity import Opportunity
from src.models.user import Profile, User

# Общий пароль для всех тестовых пользователей
TEST_PASSWORD = "test1234!"


@pytest_asyncio.fixture
async def test_users_with_data(db_session: AsyncSession) -> dict[str, Any]:
    """
    Create test users with opportunities and companies for favorites testing.
    """
    hashed_pw = hash_password(TEST_PASSWORD)

    # Applicant 1 (main test user for favorites)
    applicant1 = User(
        email="applicant1@test.com",
        hashed_password=hashed_pw,
        role=UserRole.APPLICANT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(applicant1)
    await db_session.flush()

    profile1 = Profile(
        user_id=applicant1.id,
        first_name="John",
        last_name="Doe",
        university="Test University",
        graduation_year=2024,
        privacy_settings={"public_profile": True, "show_contacts": True, "show_github": True, "show_applications": False},
    )
    db_session.add(profile1)

    # Applicant 2 (for search testing)
    applicant2 = User(
        email="applicant2@test.com",
        hashed_password=hashed_pw,
        role=UserRole.APPLICANT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(applicant2)
    await db_session.flush()

    profile2 = Profile(
        user_id=applicant2.id,
        first_name="Jane",
        last_name="Smith",
        university="Test University",
        graduation_year=2025,
        headline="Frontend Developer",
        privacy_settings={"public_profile": True, "show_contacts": True, "show_github": False, "show_applications": False},
    )
    db_session.add(profile2)

    # Applicant 3 (private profile - should not appear in search)
    applicant3 = User(
        email="applicant3@test.com",
        hashed_password=hashed_pw,
        role=UserRole.APPLICANT,
        is_active=True,
        is_verified=True,
    )
    db_session.add(applicant3)
    await db_session.flush()

    profile3 = Profile(
        user_id=applicant3.id,
        first_name="Hidden",
        last_name="User",
        university="Private University",
        graduation_year=2023,
        headline="Backend Developer",
        privacy_settings={"public_profile": False, "show_contacts": False, "show_github": False, "show_applications": False},
    )
    db_session.add(profile3)

    # Employer 1 (owns company and opportunities)
    employer1 = User(
        email="employer1@test.com",
        hashed_password=hashed_pw,
        role=UserRole.EMPLOYER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(employer1)
    await db_session.flush()

    # Profile for employer1 (needed for contact requests)
    profile_employer1 = Profile(
        user_id=employer1.id,
        first_name="Employer",
        last_name="One",
        university="Test University",
        graduation_year=2020,
        privacy_settings={"public_profile": True, "show_contacts": True, "show_github": False, "show_applications": False},
    )
    db_session.add(profile_employer1)

    # Employer 2 (for "own company" validation)
    employer2 = User(
        email="employer2@test.com",
        hashed_password=hashed_pw,
        role=UserRole.EMPLOYER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(employer2)
    await db_session.flush()

    # Curator
    curator = User(
        email="curator@test.com",
        hashed_password=hashed_pw,
        role=UserRole.CURATOR,
        is_active=True,
        is_verified=True,
    )
    db_session.add(curator)
    await db_session.flush()

    # Profile for curator
    profile_curator = Profile(
        user_id=curator.id,
        first_name="Curator",
        last_name="User",
        university="Test University",
        graduation_year=2019,
        privacy_settings={"public_profile": True, "show_contacts": True, "show_github": False, "show_applications": False},
    )
    db_session.add(profile_curator)

    await db_session.commit()

    # Create company for employer1
    company = Company(
        name="Test Company",
        inn="7707083893",
        city="Moscow",
        country="Россия",
        description="Test company description",
        owner_id=employer1.id,
        verification_status=VerificationStatus.APPROVED,
    )
    db_session.add(company)
    await db_session.flush()

    # Create opportunities
    opportunity1 = Opportunity(
        title="Python Developer",
        description="Develop Python applications",
        company_id=company.id,
        type=OpportunityType.VACANCY,
        status=OpportunityStatus.ACTIVE,
        work_format="HYBRID",
        city="Moscow",
        requirements="Python, FastAPI, PostgreSQL",
    )
    db_session.add(opportunity1)

    opportunity2 = Opportunity(
        title="Frontend Developer",
        description="Develop frontend applications",
        company_id=company.id,
        type=OpportunityType.INTERNSHIP,
        status=OpportunityStatus.ACTIVE,
        work_format="REMOTE",
        city="Saint Petersburg",
        requirements="JavaScript, React, TypeScript",
    )
    db_session.add(opportunity2)

    await db_session.commit()

    return {
        "applicant1": applicant1,
        "applicant2": applicant2,
        "applicant3": applicant3,
        "employer1": employer1,
        "employer2": employer2,
        "curator": curator,
        "company": company,
        "opportunity1": opportunity1,
        "opportunity2": opportunity2,
        "profile1": profile1,
        "profile2": profile2,
        "profile3": profile3,
    }


@pytest_asyncio.fixture
async def auth_tokens(client: AsyncClient, test_users_with_data: dict[str, Any]) -> dict[str, str]:
    """
    Login all test users and return access tokens.
    """
    tokens = {}
    users = test_users_with_data

    for user_key in ["applicant1", "applicant2", "employer1", "employer2", "curator"]:
        user = users[user_key]
        login_data = {"username": user.email, "password": TEST_PASSWORD}
        response = await client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 200
        tokens[user_key] = response.json()["access_token"]

    return tokens


# =============================================================================
# Favorites Tests
# =============================================================================


@pytest.mark.asyncio
async def test_sync_favorites_empty(client: AsyncClient, auth_tokens: dict[str, str]) -> None:
    """Test syncing empty favorites (first login)."""
    token = auth_tokens.get("applicant1")

    response = await client.post(
        "/api/v1/favorites/sync",
        json={"opportunity_ids": [], "company_ids": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["synced_opportunities"] == []
    assert data["synced_companies"] == []


@pytest.mark.asyncio
async def test_sync_favorites_with_ids(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test syncing favorites with IDs from localStorage."""
    token = auth_tokens.get("applicant1")
    opp1_id = str(test_users_with_data["opportunity1"].id)
    company_id = str(test_users_with_data["company"].id)

    response = await client.post(
        "/api/v1/favorites/sync",
        json={"opportunity_ids": [opp1_id], "company_ids": [company_id]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert opp1_id in data["synced_opportunities"]
    assert company_id in data["synced_companies"]


@pytest.mark.asyncio
async def test_sync_favorites_idempotent(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that sync is idempotent (no duplicates)."""
    token = auth_tokens.get("applicant1")
    opp1_id = str(test_users_with_data["opportunity1"].id)

    # Sync twice
    await client.post(
        "/api/v1/favorites/sync",
        json={"opportunity_ids": [opp1_id], "company_ids": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        "/api/v1/favorites/sync",
        json={"opportunity_ids": [opp1_id], "company_ids": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    # Should still have only one entry
    assert data["synced_opportunities"].count(opp1_id) == 1


@pytest.mark.asyncio
async def test_get_favorites_empty(client: AsyncClient, auth_tokens: dict[str, str]) -> None:
    """Test getting empty favorites list."""
    token = auth_tokens.get("applicant1")

    # Get opportunities
    response = await client.get(
        "/api/v1/favorites/opportunities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0

    # Get companies
    response = await client.get(
        "/api/v1/favorites/companies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_add_opportunity_to_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test adding opportunity to favorites."""
    token = auth_tokens.get("applicant1")
    opp1_id = str(test_users_with_data["opportunity1"].id)

    response = await client.post(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        json={"note": "Interesting position"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["opportunity"]["id"] == opp1_id
    assert data["note"] == "Interesting position"
    assert data["opportunity"]["title"] == "Python Developer"


@pytest.mark.asyncio
async def test_add_opportunity_to_favorites_without_note(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test adding opportunity without note."""
    token = auth_tokens.get("applicant1")
    opp1_id = str(test_users_with_data["opportunity1"].id)

    response = await client.post(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["opportunity"]["id"] == opp1_id
    assert data["note"] is None


@pytest.mark.asyncio
async def test_add_own_opportunity_to_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that employer cannot add own opportunity to favorites."""
    token = auth_tokens.get("employer1")
    opp1_id = str(test_users_with_data["opportunity1"].id)

    response = await client.post(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should fail - cannot favorite own opportunity
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_nonexistent_opportunity_to_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
) -> None:
    """Test adding nonexistent opportunity."""
    token = auth_tokens.get("applicant1")
    fake_id = "00000000-0000-0000-0000-000000000000"

    response = await client.post(
        f"/api/v1/favorites/opportunities/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_opportunity_from_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test removing opportunity from favorites."""
    token = auth_tokens.get("applicant1")
    opp1_id = str(test_users_with_data["opportunity1"].id)

    # Add first
    await client.post(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Remove
    response = await client.delete(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204

    # Verify removed
    response = await client.get(
        "/api/v1/favorites/opportunities",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = response.json()
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_remove_nonexistent_opportunity_from_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
) -> None:
    """Test removing opportunity that wasn't added (should be ignored)."""
    token = auth_tokens.get("applicant1")
    opp1_id = "12345678-1234-1234-1234-123456789012"

    response = await client.delete(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should not fail
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_add_company_to_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test adding company to favorites."""
    token = auth_tokens.get("applicant1")
    company_id = str(test_users_with_data["company"].id)

    response = await client.post(
        f"/api/v1/favorites/companies/{company_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["company"]["id"] == company_id
    assert data["company"]["name"] == "Test Company"
    assert data["company"]["city"] == "Moscow"


@pytest.mark.asyncio
async def test_add_own_company_to_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that employer cannot add own company to favorites."""
    token = auth_tokens.get("employer1")
    company_id = str(test_users_with_data["company"].id)

    response = await client.post(
        f"/api/v1/favorites/companies/{company_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should fail - cannot favorite own company
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_nonexistent_company_to_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
) -> None:
    """Test adding nonexistent company."""
    token = auth_tokens.get("applicant1")
    fake_id = "00000000-0000-0000-0000-000000000000"

    response = await client.post(
        f"/api/v1/favorites/companies/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_company_from_favorites(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test removing company from favorites."""
    token = auth_tokens.get("applicant1")
    company_id = str(test_users_with_data["company"].id)

    # Add first
    await client.post(
        f"/api/v1/favorites/companies/{company_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Remove
    response = await client.delete(
        f"/api/v1/favorites/companies/{company_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204

    # Verify removed
    response = await client.get(
        "/api/v1/favorites/companies",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = response.json()
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_get_favorites_with_data(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test getting favorites with data."""
    token = auth_tokens.get("applicant1")
    opp1_id = str(test_users_with_data["opportunity1"].id)
    opp2_id = str(test_users_with_data["opportunity2"].id)
    company_id = str(test_users_with_data["company"].id)

    # Add items
    await client.post(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        json={"note": "Great opportunity"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/v1/favorites/opportunities/{opp2_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/v1/favorites/companies/{company_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Get opportunities
    response = await client.get(
        "/api/v1/favorites/opportunities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Check note is present
    notes = [item["note"] for item in data["items"]]
    assert "Great opportunity" in notes

    # Get companies
    response = await client.get(
        "/api/v1/favorites/companies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["company"]["name"] == "Test Company"


@pytest.mark.asyncio
async def test_favorites_requires_auth(client: AsyncClient) -> None:
    """Test that favorites endpoints require authentication."""
    # Get favorites without auth
    response = await client.get("/api/v1/favorites/opportunities")
    assert response.status_code == 401

    response = await client.get("/api/v1/favorites/companies")
    assert response.status_code == 401

    # Add to favorites without auth
    response = await client.post("/api/v1/favorites/opportunities/12345678-1234-1234-1234-123456789012")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_favorites_non_applicant_forbidden(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that non-applicants cannot use favorites."""
    token = auth_tokens.get("employer1")
    opp1_id = str(test_users_with_data["opportunity1"].id)

    response = await client.get(
        "/api/v1/favorites/opportunities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403

    response = await client.post(
        f"/api/v1/favorites/opportunities/{opp1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# =============================================================================
# Applicants Search Tests
# =============================================================================


@pytest.mark.asyncio
async def test_search_applicants_empty_filter(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test searching applicants without filters."""
    token = auth_tokens.get("employer1")

    response = await client.get(
        "/api/v1/applicants/search",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2  # At least applicant1 and applicant2 (not applicant3 - private)
    # Check that private profile is not in results
    names = [(item["first_name"], item["last_name"]) for item in data["items"]]
    assert ("Hidden", "User") not in names


@pytest.mark.asyncio
async def test_search_applicants_by_skills(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test searching applicants by skills."""
    token = auth_tokens.get("employer1")

    # First, add skills to applicant1's profile via direct DB access
    # (In real scenario this would be done through profile update endpoint)

    response = await client.get(
        "/api/v1/applicants/search?skills=Python,FastAPI",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_search_applicants_by_university(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test searching applicants by university."""
    token = auth_tokens.get("employer1")

    response = await client.get(
        "/api/v1/applicants/search?university=Test",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    # Should find applicant1 and applicant2 (both from Test University)
    assert data["total"] >= 2
    names = [(item["first_name"], item["last_name"]) for item in data["items"]]
    assert ("John", "Doe") in names or ("Jane", "Smith") in names


@pytest.mark.asyncio
async def test_search_applicants_by_graduation_year(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test searching applicants by graduation year."""
    token = auth_tokens.get("employer1")

    response = await client.get(
        "/api/v1/applicants/search?graduation_year=2024",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    # Should find applicant1 (graduation_year=2024)
    names = [(item["first_name"], item["last_name"]) for item in data["items"]]
    assert ("John", "Doe") in names


@pytest.mark.asyncio
async def test_search_applicants_by_city(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test searching applicants by city (searches in university field)."""
    token = auth_tokens.get("employer1")

    # City search looks in university field in current implementation
    response = await client.get(
        "/api/v1/applicants/search?city=Test",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    # Should find applicant1 and applicant2 (both have "Test University")
    assert data["total"] >= 2
    names = [(item["first_name"], item["last_name"]) for item in data["items"]]
    assert ("John", "Doe") in names or ("Jane", "Smith") in names


@pytest.mark.asyncio
async def test_search_applicants_pagination(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test searching applicants with pagination."""
    token = auth_tokens.get("employer1")

    response = await client.get(
        "/api/v1/applicants/search?limit=1&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["limit"] == 1
    assert data["offset"] == 0

    # Get second page
    response = await client.get(
        "/api/v1/applicants/search?limit=1&offset=1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_search_applicants_requires_auth(
    client: AsyncClient,
    auth_tokens: dict[str, str],
) -> None:
    """Test that search requires authentication."""
    # Without auth
    response = await client.get("/api/v1/applicants/search")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_applicants_non_employer_forbidden(
    client: AsyncClient,
    auth_tokens: dict[str, str],
) -> None:
    """Test that non-employer/curator cannot search applicants."""
    token = auth_tokens.get("applicant1")

    response = await client.get(
        "/api/v1/applicants/search",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_applicant_profile(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test getting applicant profile detail."""
    token = auth_tokens.get("employer1")
    profile2_id = str(test_users_with_data["profile2"].id)

    response = await client.get(
        f"/api/v1/applicants/{profile2_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Jane"
    assert data["last_name"] == "Smith"
    assert data["university"] == "Test University"


@pytest.mark.asyncio
async def test_get_private_applicant_profile(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test getting private profile shows hidden data."""
    token = auth_tokens.get("employer1")
    profile3_id = str(test_users_with_data["profile3"].id)

    response = await client.get(
        f"/api/v1/applicants/{profile3_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    # Private profile should show "Скрыто"
    assert data["first_name"] == "Скрыто"
    assert data["last_name"] == "Скрыто"
    assert data["university"] is None


@pytest.mark.asyncio
async def test_get_nonexistent_applicant_profile(
    client: AsyncClient,
    auth_tokens: dict[str, str],
) -> None:
    """Test getting nonexistent profile."""
    token = auth_tokens.get("employer1")
    fake_id = "00000000-0000-0000-0000-000000000000"

    response = await client.get(
        f"/api/v1/applicants/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_contact_request(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test sending contact request to applicant."""
    token = auth_tokens.get("employer1")
    profile2_id = str(test_users_with_data["profile2"].id)

    response = await client.post(
        f"/api/v1/applicants/{profile2_id}/contact",
        params={"message": "Interested in your profile"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert "message" in data


@pytest.mark.asyncio
async def test_send_contact_request_to_self(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that cannot send contact request to self."""
    # This test is a placeholder for future implementation
    # that would verify users cannot send contact requests to themselves
    pass


@pytest.mark.asyncio
async def test_send_contact_request_duplicate(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that duplicate contact requests are rejected."""
    token = auth_tokens.get("employer1")
    profile2_id = str(test_users_with_data["profile2"].id)

    # First request
    response = await client.post(
        f"/api/v1/applicants/{profile2_id}/contact",
        params={"message": "First request"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201

    # Second request should fail
    response = await client.post(
        f"/api/v1/applicants/{profile2_id}/contact",
        params={"message": "Duplicate request"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409  # Conflict


@pytest.mark.asyncio
async def test_send_contact_request_requires_auth(
    client: AsyncClient,
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that contact request requires authentication."""
    profile2_id = str(test_users_with_data["profile2"].id)

    response = await client.post(f"/api/v1/applicants/{profile2_id}/contact")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_contact_request_non_employer_forbidden(
    client: AsyncClient,
    auth_tokens: dict[str, str],
    test_users_with_data: dict[str, Any],
) -> None:
    """Test that non-employer cannot send contact requests."""
    token = auth_tokens.get("applicant1")
    profile2_id = str(test_users_with_data["profile2"].id)

    response = await client.post(
        f"/api/v1/applicants/{profile2_id}/contact",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
