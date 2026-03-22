import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import UserRole


@pytest.mark.asyncio
async def test_get_current_user_data(client: AsyncClient) -> None:
    """
    Тест получения данных текущего пользователя.
    """
    # Регистрируемся
    user_data = {
        "email": "test_user_me@example.com",
        "password": "TestPassw0rd_123!",
        "first_name": "Test",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    reg_response = await client.post("/api/v1/auth/register", json=user_data)
    assert reg_response.status_code == status.HTTP_201_CREATED

    access_token = reg_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Получаем данные пользователя
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["role"] == user_data["role"]
    assert data["profile"]["first_name"] == user_data["first_name"]
    assert data["profile"]["last_name"] == user_data["last_name"]


@pytest.mark.asyncio
async def test_update_user_profile(client: AsyncClient) -> None:
    """
    Тест обновления профиля пользователя.
    """
    # Регистрируемся
    user_data = {
        "email": "test_update@example.com",
        "password": "TestPassw0rd_123!",
        "first_name": "Test",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    reg_response = await client.post("/api/v1/auth/register", json=user_data)
    assert reg_response.status_code == status.HTTP_201_CREATED

    access_token = reg_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    update_data = {
        "first_name": "Updated",
        "last_name": "Name",
        "university": "Test University",
        "graduation_year": 2025,
        "skills": ["Python", "FastAPI"],
        "social_links": {"github": "https://github.com/test"},
    }

    response = await client.patch("/api/v1/users/me", json=update_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["profile"]["first_name"] == update_data["first_name"]
    assert data["profile"]["last_name"] == update_data["last_name"]
    assert data["profile"]["university"] == update_data["university"]
    assert data["profile"]["graduation_year"] == update_data["graduation_year"]
    assert data["profile"]["skills"] == update_data["skills"]
    assert data["profile"]["social_links"] == update_data["social_links"]


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient) -> None:
    """
    Тест смены пароля.
    """
    user_data = {
        "email": "test_change_pwd@example.com",
        "password": "OldPassw0rd_123!",
        "first_name": "Test",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    reg_response = await client.post("/api/v1/auth/register", json=user_data)
    assert reg_response.status_code == status.HTTP_201_CREATED

    access_token = reg_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    change_data = {
        "old_password": "OldPassw0rd_123!",
        "new_password": "NewPassw0rd_456!",
    }

    response = await client.post(
        "/api/v1/users/me/change-password", json=change_data, headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Password changed successfully"

    login_data = {"username": user_data["email"], "password": "OldPassw0rd_123!"}
    old_login_response = await client.post("/api/v1/auth/login", data=login_data)
    assert old_login_response.status_code == status.HTTP_401_UNAUTHORIZED

    new_login_data = {"username": user_data["email"], "password": "NewPassw0rd_456!"}
    new_login_response = await client.post("/api/v1/auth/login", data=new_login_data)
    assert new_login_response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_change_password_invalid_old(client: AsyncClient) -> None:
    """
    Тест смены пароля с неверным старым паролем.
    """
    user_data = {
        "email": "test_invalid_old@example.com",
        "password": "C0rrect_Passw0rd_123!",
        "first_name": "Test",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    reg_response = await client.post("/api/v1/auth/register", json=user_data)
    access_token = reg_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    change_data = {
        "old_password": "wrong_password",
        "new_password": "NewPassw0rd_456!",
    }

    response = await client.post(
        "/api/v1/users/me/change-password", json=change_data, headers=headers
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_password_reset_request(client: AsyncClient) -> None:
    """
    Тест запроса сброса пароля.
    """
    user_data = {
        "email": "test_reset@example.com",
        "password": "TestPassw0rd_123!",
        "first_name": "Test",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    await client.post("/api/v1/auth/register", json=user_data)

    reset_request = {"email": "test_reset@example.com"}
    response = await client.post("/api/v1/auth/password-reset", json=reset_request)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "message" in data
    assert "token" not in data


@pytest.mark.asyncio
async def test_password_reset_confirm(client: AsyncClient, db_session: AsyncSession) -> None:
    """
    Тест подтверждения сброса пароля.
    """
    user_data = {
        "email": "test_reset_confirm@example.com",
        "password": "TestPassw0rd_123!",
        "first_name": "Test",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    await client.post("/api/v1/auth/register", json=user_data)

    reset_request = {"email": "test_reset_confirm@example.com"}
    reset_response = await client.post("/api/v1/auth/password-reset", json=reset_request)
    assert reset_response.status_code == status.HTTP_200_OK
    assert "token" not in reset_response.json()

    from datetime import timedelta

    from sqlalchemy import select

    from src.core.security import _create_token
    from src.models.user import User

    result = await db_session.execute(
        select(User).where(User.email == "test_reset_confirm@example.com")
    )
    user = result.scalar_one_or_none()

    if user:
        reset_token = _create_token(
            str(user.id),
            timedelta(hours=1),
            token_type="password_reset",
        )

        reset_confirm = {
            "token": reset_token,
            "new_password": "NewPassw0rd_456!",
        }

        response = await client.post("/api/v1/auth/password-reset/confirm", json=reset_confirm)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Password has been reset successfully"

        login_data = {"username": user_data["email"], "password": "NewPassw0rd_456!"}
        login_response = await client.post("/api/v1/auth/login", data=login_data)
        assert login_response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_create_curator_by_admin(client: AsyncClient) -> None:
    """
    Тест создания куратора администратором.
    """
    admin_data = {
        "email": "admin_test@example.com",
        "password": "Adm1n_T3st_Passw0rd!",
        "first_name": "Admin",
        "last_name": "User",
        "role": str(UserRole.CURATOR),
    }

    admin_response = await client.post("/api/v1/auth/register", json=admin_data)
    assert admin_response.status_code == status.HTTP_201_CREATED
    admin_token = admin_response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    curator_data = {
        "email": "curator@example.com",
        "password": "Curat0r_Passw0rd_123!",
        "first_name": "Curator",
        "last_name": "User",
    }

    response = await client.post("/api/v1/users/curators", json=curator_data, headers=admin_headers)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["email"] == curator_data["email"]
    assert data["role"] == str(UserRole.CURATOR)
    assert data["is_verified"] is True


@pytest.mark.asyncio
async def test_create_curator_by_non_admin(client: AsyncClient) -> None:
    """
    Тест попытки создания куратора не-администратором.
    """
    user_data = {
        "email": "regular_user@example.com",
        "password": "R3gul4r_Us3r_Passw0rd!",
        "first_name": "Regular",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    user_response = await client.post("/api/v1/auth/register", json=user_data)
    user_token = user_response.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    curator_data = {
        "email": "curator2@example.com",
        "password": "Curat0r_Passw0rd!",
        "first_name": "Curator",
        "last_name": "User",
    }

    response = await client.post("/api/v1/users/curators", json=curator_data, headers=user_headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_verify_employer_by_curator(client: AsyncClient) -> None:
    """
    Тест верификации работодателя куратором.
    """
    admin_data = {
        "email": "admin_verify@example.com",
        "password": "Adm1n_Passw0rd!",
        "first_name": "Admin",
        "last_name": "User",
        "role": str(UserRole.CURATOR),
    }

    admin_response = await client.post("/api/v1/auth/register", json=admin_data)
    admin_token = admin_response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    employer_data = {
        "email": "employer@example.com",
        "password": "Empl0yer_Passw0rd!",
        "first_name": "Employer",
        "last_name": "Company",
        "role": str(UserRole.EMPLOYER),
    }

    employer_response = await client.post("/api/v1/auth/register", json=employer_data)
    employer_id = employer_response.json()["user"]["id"]

    verify_data = {"is_verified": True}
    response = await client.patch(
        f"/api/v1/users/employers/{employer_id}/verify",
        json=verify_data,
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["is_verified"] is True
    assert data["role"] == str(UserRole.EMPLOYER)


@pytest.mark.asyncio
async def test_verify_non_employer(client: AsyncClient) -> None:
    """
    Тест попытки верификации не-работодателя.
    """
    admin_data = {
        "email": "admin_verify2@example.com",
        "password": "Adm1n_Passw0rd_2!",
        "first_name": "Admin",
        "last_name": "User",
        "role": str(UserRole.CURATOR),
    }

    admin_response = await client.post("/api/v1/auth/register", json=admin_data)
    admin_token = admin_response.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    applicant_data = {
        "email": "applicant@example.com",
        "password": "Appl1c4nt_Passw0rd!",
        "first_name": "Applicant",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    applicant_response = await client.post("/api/v1/auth/register", json=applicant_data)
    applicant_id = applicant_response.json()["user"]["id"]

    verify_data = {"is_verified": True}
    response = await client.patch(
        f"/api/v1/users/employers/{applicant_id}/verify",
        json=verify_data,
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_logout(client: AsyncClient) -> None:
    """
    Тест выхода из системы с инвалидацией токенов.
    """
    user_data = {
        "email": "test_logout@example.com",
        "password": "TestL0g0ut_Passw0rd!",
        "first_name": "Test",
        "last_name": "User",
        "role": str(UserRole.APPLICANT),
    }

    reg_response = await client.post("/api/v1/auth/register", json=user_data)
    assert reg_response.status_code == status.HTTP_201_CREATED

    access_token = reg_response.json()["access_token"]
    refresh_token = reg_response.json()["refresh_token"]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Refresh-Token": refresh_token,
    }

    response = await client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Successfully logged out"


@pytest.mark.asyncio
async def test_logout_missing_authorization(client: AsyncClient) -> None:
    """
    Тест выхода без заголовка Authorization.
    """
    headers = {"X-Refresh-Token": "some_refresh_token"}

    response = await client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_logout_missing_refresh_token(client: AsyncClient) -> None:
    """
    Тест выхода без refresh токена.
    """
    headers = {"Authorization": "Bearer some_access_token"}

    response = await client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
