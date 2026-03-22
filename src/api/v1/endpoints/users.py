import structlog
from fastapi import APIRouter, Depends, status

from src.api.v1.deps import RoleChecker, get_current_user, get_user_service
from src.models.enums import UserRole
from src.models.user import User
from src.schemas.user import (
    CuratorCreate,
    EmployerVerifyRequest,
    PasswordChangeRequest,
    UserResponse,
    UserUpdate,
)
from src.services.user import UserService

logger = structlog.get_logger()

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Получение данных текущего пользователя",
    description="Возвращает данные авторизованного пользователя включая профиль.",
)
async def get_current_user_data(
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """
    Получение данных текущего пользователя.

    Возвращает полную информацию о пользователе включая профиль,
    роль, статус верификации и настройки приватности.
    """
    user_with_profile = await user_service.get_user_with_profile(str(current_user.id))
    return UserResponse.model_validate(user_with_profile)


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Обновление профиля пользователя",
    description="Редактирование ФИО, навыков, ссылок и настроек приватности.",
)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """
    Обновление профиля текущего пользователя.

    Позволяет изменить:
    - ФИО (first_name, last_name)
    - Учебное заведение и год выпуска
    - Навыки (skills)
    - Социальные ссылки (social_links)
    - Настройки приватности (privacy_settings)
    """
    updated_user = await user_service.update_user_profile(
        user_id=str(current_user.id),
        user_update=user_update,
    )
    return UserResponse.model_validate(updated_user)


@router.post(
    "/me/change-password",
    status_code=status.HTTP_200_OK,
    summary="Смена пароля",
    description="Изменение пароля текущего пользователя. Требуется старый и новый пароль.",
)
async def change_password(
    password_request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """
    Смена пароля текущего пользователя.

    Требует ввода текущего пароля для подтверждения,
    затем устанавливает новый пароль.
    """
    await user_service.change_password(
        user_id=str(current_user.id),
        password_request=password_request,
    )
    return {"message": "Password changed successfully"}


# Эндпоинты для кураторов (только для администраторов)
require_admin = RoleChecker([UserRole.CURATOR])


@router.post(
    "/curators",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание куратора",
    description="Создание учетной записи куратора. Доступно только администратору.",
    dependencies=[Depends(require_admin)],
)
async def create_curator(
    curator_data: CuratorCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """
    Создание нового куратора платформы.

    Доступно только пользователям с ролью CURATOR (администратор).
    Создает пользователя с ролью CURATOR и автоматически верифицирует.
    """
    user = await user_service.create_curator(curator_data)
    return UserResponse.model_validate(user)


@router.patch(
    "/employers/{employer_id}/verify",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Верификация работодателя",
    description="Изменение статуса верификации работодателя. Доступно только куратору.",
    dependencies=[Depends(require_admin)],
)
async def verify_employer(
    employer_id: str,
    verify_data: EmployerVerifyRequest,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """
    Верификация работодателя куратором.

    Позволяет куратору изменить статус верификации пользователя с ролью EMPLOYER.
    Требуется для доступа работодателей к публикации вакансий.
    """
    user = await user_service.verify_employer(
        employer_id=employer_id,
        is_verified=verify_data.is_verified,
    )
    return UserResponse.model_validate(user)
