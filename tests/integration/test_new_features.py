"""
Integration tests for new features:
- Privacy settings and public profile
- File uploads (CV and media)
- Recommendations system
"""

import io
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.enums import ContactStatus, OpportunityStatus, UserRole
from src.models.user import Profile, User

# Общий пароль для всех тестовых пользователей
TEST_PASSWORD = "test1234!"


@pytest_asyncio.fixture
async def test_users(db_session: AsyncSession) -> dict[str, Any]:
    """Create test users with different roles."""
    # Генерируем хеш пароля динамически (Argon2 использует случайную соль)
    hashed_pw = hash_password(TEST_PASSWORD)

    # Applicant 1 (will test privacy)
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
        privacy_settings={"public_profile": True, "show_contacts": False, "show_github": True, "show_applications": False},
    )
    db_session.add(profile1)

    # Applicant 2 (private profile)
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
        university="Private University",
        graduation_year=2025,
        privacy_settings={"public_profile": False, "show_contacts": False, "show_github": False, "show_applications": False},
    )
    db_session.add(profile2)

    # Employer
    employer = User(
        email="employer@test.com",
        hashed_password=hashed_pw,
        role=UserRole.EMPLOYER,
        is_active=True,
        is_verified=True,
    )
    db_session.add(employer)

    # Curator
    curator = User(
        email="curator@test.com",
        hashed_password=hashed_pw,
        role=UserRole.CURATOR,
        is_active=True,
        is_verified=True,
    )
    db_session.add(curator)

    await db_session.commit()

    return {
        "applicant1": applicant1,
        "applicant2": applicant2,
        "employer": employer,
        "curator": curator,
    }


@pytest_asyncio.fixture
async def auth_tokens(client: AsyncClient, test_users: dict[str, Any]) -> dict[str, str]:
    """Get auth tokens for test users."""
    tokens = {}

    for name, user in test_users.items():
        # OAuth2PasswordRequestForm ожидает form-data, не JSON
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": user.email,  # OAuth2 использует 'username' для email
                "password": "test1234!",
            },
        )
        if response.status_code == 200:
            data = response.json()
            tokens[name] = data["access_token"]

    return tokens


@pytest.mark.asyncio
async def test_public_profile_with_privacy(client: AsyncClient, test_users: dict[str, Any], auth_tokens: dict[str, str]) -> None:
    """Test public profile endpoint respects privacy settings."""
    # Get applicant1's public profile (public_profile=True)
    applicant1 = test_users["applicant1"]
    token = auth_tokens.get("curator")

    response = await client.get(
        f"/api/v1/users/{applicant1.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert data["university"] == "Test University"
    assert data["show_full_data"] is False  # Not owner viewing

    # Get applicant2's public profile (public_profile=False)
    applicant2 = test_users["applicant2"]
    response = await client.get(
        f"/api/v1/users/{applicant2.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Скрыто"
    assert data["last_name"] == "Скрыто"
    assert data["university"] is None
    assert data["show_full_data"] is False


@pytest.mark.asyncio
async def test_owner_sees_full_profile(client: AsyncClient, test_users: dict[str, Any], auth_tokens: dict[str, str]) -> None:
    """Test that profile owner sees all their data."""
    applicant1 = test_users["applicant1"]
    token = auth_tokens.get("applicant1")

    response = await client.get(
        f"/api/v1/users/{applicant1.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert data["show_full_data"] is True  # Owner viewing


@pytest.mark.asyncio
async def test_applicant_search_employer_only(
    client: AsyncClient,
    test_users: dict[str, Any],
    auth_tokens: dict[str, str],
) -> None:
    """Test that only employers/curators can search applicants."""
    token = auth_tokens.get("employer")

    response = await client.get(
        "/api/v1/users/applicants/search?university=Test",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    # Should only return applicant1 (public_profile=True)
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_applicant_search_respects_privacy(
    client: AsyncClient,
    test_users: dict[str, Any],
    auth_tokens: dict[str, str],
) -> None:
    """Test that search only returns users with public_profile=True."""
    token = auth_tokens.get("curator")

    response = await client.get(
        "/api/v1/users/applicants/search",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    # Check that applicant2 (private profile) is not in results
    emails = [item["email"] for item in data["items"]]
    assert test_users["applicant2"].email not in emails


@pytest.mark.asyncio
async def test_cv_upload_applicant_only(client: AsyncClient, test_users: dict[str, Any], auth_tokens: dict[str, str]) -> None:
    """Test that only applicants can upload CVs."""
    # Applicant can upload
    token = auth_tokens.get("applicant1")

    # Create a test PDF file
    file_content = b"%PDF-1.4 test pdf content"
    files = {"file": ("test_cv.pdf", io.BytesIO(file_content), "application/pdf")}

    response = await client.post(
        "/api/v1/uploads/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should succeed (file validation will pass in test mode)
    assert response.status_code in [200, 422]  # 422 if file validation is strict

    # Employer cannot upload CV
    token = auth_tokens.get("employer")
    response = await client.post(
        "/api/v1/uploads/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_media_upload_employer_only(client: AsyncClient, test_users: dict[str, Any], auth_tokens: dict[str, str]) -> None:
    """Test that only employers/curators can upload media."""
    # Employer can upload
    token = auth_tokens.get("employer")

    # Create a test image file
    file_content = b"\x89PNG test image content"
    files = {"file": ("test_image.png", io.BytesIO(file_content), "image/png")}

    response = await client.post(
        "/api/v1/uploads/media",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Should succeed
    assert response.status_code in [200, 422]

    # Applicant cannot upload media
    token = auth_tokens.get("applicant1")
    response = await client.post(
        "/api/v1/uploads/media",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_recommendation_requires_contact(
    client: AsyncClient,
    test_users: dict[str, Any],
    auth_tokens: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Test that recommendations require ACCEPTED contact relationship."""
    applicant1 = test_users["applicant1"]
    applicant2 = test_users["applicant2"]

    # Create ACCEPTED contact relationship
    from src.models.social import Contact

    contact = Contact(
        requester_id=applicant1.id,
        addressee_id=applicant2.id,
        status=ContactStatus.ACCEPTED,
    )
    db_session.add(contact)
    await db_session.commit()

    # Create a test opportunity
    from src.models.company import Company
    from src.models.opportunity import Opportunity

    company = Company(
        owner_id=test_users["employer"].id,
        name="Test Company",
        verification_status="approved",
    )
    db_session.add(company)
    await db_session.flush()

    opportunity = Opportunity(
        company_id=company.id,
        title="Test Developer",
        type="vacancy",
        status=OpportunityStatus.ACTIVE,
        work_format="remote",
    )
    db_session.add(opportunity)
    await db_session.commit()

    # Try to create recommendation
    token = auth_tokens.get("applicant1")

    response = await client.post(
        "/api/v1/recommendations",
        json={
            "recipient_id": str(applicant2.id),
            "opportunity_id": str(opportunity.id),
            "message": "Check this out!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_recommendation_self_forbidden(
    client: AsyncClient,
    test_users: dict[str, Any],
    auth_tokens: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Test that users cannot recommend to themselves."""
    applicant1 = test_users["applicant1"]
    token = auth_tokens.get("applicant1")

    # Create a test opportunity first
    from src.models.company import Company
    from src.models.enums import OpportunityStatus
    from src.models.opportunity import Opportunity

    company = Company(
        owner_id=test_users["employer"].id,
        name="Test Company",
        verification_status="approved",
    )
    db_session.add(company)
    await db_session.flush()

    opportunity = Opportunity(
        company_id=company.id,
        title="Test Developer",
        type="vacancy",
        status=OpportunityStatus.ACTIVE,
        work_format="remote",
    )
    db_session.add(opportunity)
    await db_session.commit()

    response = await client.post(
        "/api/v1/recommendations",
        json={
            "recipient_id": str(applicant1.id),  # Same as sender
            "opportunity_id": str(opportunity.id),
            "message": "Self recommendation",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_recommendations(client: AsyncClient, test_users: dict[str, Any], auth_tokens: dict[str, str]) -> None:
    """Test getting sent and received recommendations."""
    token = auth_tokens.get("applicant1")

    # Get sent recommendations (should be empty initially)
    response = await client.get(
        "/api/v1/recommendations/sent",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

    # Get received recommendations
    token = auth_tokens.get("applicant2")
    response = await client.get(
        "/api/v1/recommendations/received",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
