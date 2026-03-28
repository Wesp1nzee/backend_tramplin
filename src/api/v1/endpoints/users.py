from fastapi import APIRouter, Depends, Query, status

from src.api.v1.deps import RoleChecker, get_current_user, get_user_service
from src.models.enums import UserRole
from src.models.user import User
from src.schemas.user import (
    ApplicantPublicProfile,
    ApplicantSearchItem,
    ApplicantSearchResponse,
    CuratorCreate,
    EmployerVerifyRequest,
    PasswordChangeRequest,
    ProfileResponse,
    UserResponse,
    UserUpdate,
)
from src.services.user import PrivacyFilterService, UserService

router = APIRouter(prefix="/users", tags=["Users"])


def _build_user_response(user: User) -> UserResponse:
    """
    Build UserResponse with skills extracted from profile_skills relationship.

    Pydantic's from_attributes doesn't handle nested relationships well,
    so we manually extract skills from the ProfileSkill relationship.
    """
    profile_data = None
    if user.profile:
        profile_data = ProfileResponse(
            first_name=user.profile.first_name,
            last_name=user.profile.last_name,
            middle_name=user.profile.middle_name,
            university=user.profile.university,
            graduation_year=user.profile.graduation_year,
            social_links=user.profile.social_links or {},
            privacy_settings=user.profile.privacy_settings or {},
            skills=[ps.skill.name for ps in user.profile.profile_skills if hasattr(ps, "skill")],
        )

    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_verified=user.is_verified,
        created_at=user.created_at,
        profile=profile_data,
    )


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
    return _build_user_response(user_with_profile)


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
    return _build_user_response(updated_user)


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


@router.get(
    "/{user_id}",
    response_model=ApplicantPublicProfile,
    status_code=status.HTTP_200_OK,
    summary="Публичный профиль пользователя",
    description="Получение публичного профиля пользователя с учётом настроек приватности.",
)
async def get_public_user_profile(
    user_id: str,
    current_user: User | None = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> ApplicantPublicProfile:
    """
    Получение публичного профиля пользователя.

    Возвращает данные профиля с применёнными настройками приватности:
    - Если public_profile=False: скрывает имя, контакты, CV
    - Если show_contacts=False: скрывает телефон и соцсети
    - Владелец профиля видит все данные полностью

    Требуется авторизация (любой авторизованный пользователь).
    """
    user_with_profile = await user_service.get_user_with_profile(user_id)

    if not user_with_profile or not user_with_profile.profile:
        from src.core.exceptions import NotFoundError

        raise NotFoundError(detail="User profile not found")

    # Применяем фильтры приватности
    filtered_profile = PrivacyFilterService.apply_privacy_filters(
        profile=user_with_profile.profile,
        viewer=current_user,
    )

    return ApplicantPublicProfile(
        id=user_with_profile.id,
        **filtered_profile,
    )


# Эндпоинты для поиска соискателей (только для работодателей и кураторов)
require_employer_or_curator = RoleChecker([UserRole.EMPLOYER, UserRole.CURATOR])


@router.get(
    "/applicants/search",
    response_model=ApplicantSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Поиск соискателей",
    description="Поиск соискателей по навыкам, вузу, году выпуска и городу. Доступно только работодателям и кураторам.",
    dependencies=[Depends(require_employer_or_curator)],
)
async def search_applicants(
    skills: str | None = Query(None, description="Навыки через запятую (например: Python,Django,PostgreSQL)"),
    university: str | None = Query(None, description="Название вуза"),
    graduation_year: int | None = Query(None, ge=1990, le=2100, description="Год выпуска"),
    city: str | None = Query(None, description="Город"),
    limit: int = Query(default=50, ge=1, le=100, description="Лимит записей"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    user_service: UserService = Depends(get_user_service),
) -> ApplicantSearchResponse:
    """
    Поиск соискателей по фильтрам.

    Доступно только пользователям с ролями EMPLOYER и CURATOR.
    Возвращает только соискателей с public_profile=True.

    Параметры:
    - skills: Список навыков через запятую
    - university: Название вуза (частичное совпадение)
    - graduation_year: Год выпуска
    - city: Город
    - limit: Лимит записей (1-100)
    - offset: Смещение для пагинации
    """
    # Парсим навыки из строки
    skills_list = skills.split(",") if skills else None

    # Поиск через репозиторий
    users, total = await user_service.user_repo.search_applicants(
        skills=skills_list,
        university=university,
        graduation_year=graduation_year,
        city=city,
        limit=limit,
        offset=offset,
    )

    # Формируем ответ
    items = []
    for user in users:
        if user.profile:
            items.append(
                ApplicantSearchItem(
                    id=user.id,
                    email=user.email,
                    first_name=user.profile.first_name,
                    last_name=user.profile.last_name,
                    university=user.profile.university,
                    graduation_year=user.profile.graduation_year,
                    skills=[ps.skill.name for ps in user.profile.profile_skills if hasattr(ps, "skill")],
                    avatar_url=user.profile.avatar_url,
                    headline=user.profile.headline,
                )
            )

    return ApplicantSearchResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


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
