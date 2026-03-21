import pytest
from fastapi import status
from httpx import AsyncClient

from src.models.enums import UserRole


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient) -> None:
    """
    Интеграционный тест полного цикла:
    Регистрация -> Ошибка дубликата -> Логин.
    """
    user_data = {
        "email": "test@example.com",
        "password": "very_strong_password_123",
        "first_name": "Aleksey",
        "last_name": "Dev",
        "role": str(UserRole.APPLICANT),
    }

    reg_response = await client.post("/api/v1/auth/register", json=user_data)

    assert reg_response.status_code == status.HTTP_201_CREATED

    data = reg_response.json()

    assert data["user"]["email"] == user_data["email"]
    assert data["user"]["role"] == user_data["role"]
    assert "access_token" in data
    assert "refresh_token" in data

    profile = data["user"]["profile"]
    assert profile["first_name"] == user_data["first_name"]
    assert profile["last_name"] == user_data["last_name"]
    assert isinstance(profile["social_links"], dict)
    assert isinstance(profile["skills"], list)

    dup_response = await client.post("/api/v1/auth/register", json=user_data)
    assert dup_response.status_code == status.HTTP_409_CONFLICT

    login_data = {"username": user_data["email"], "password": user_data["password"]}
    login_response = await client.post("/api/v1/auth/login", data=login_data)

    assert login_response.status_code == status.HTTP_200_OK

    login_json = login_response.json()
    assert "access_token" in login_json
    assert login_json["token_type"].lower() == "bearer"
    assert "user" in login_json


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient) -> None:
    """
    Проверка обработки неверных учетных данных.
    """
    login_data = {"username": "nonexistent@email.com", "password": "wrongpassword"}
    response = await client.post("/api/v1/auth/login", data=login_data)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
