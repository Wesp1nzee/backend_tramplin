import structlog

from src.core.exceptions import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    UserAlreadyExistsError,
)
from src.core.security import hash_password, verify_password
from src.models.enums import UserRole
from src.models.user import User
from src.repositories.user import UserRepository
from src.schemas.user import CuratorCreate, PasswordChangeRequest, UserUpdate

logger = structlog.get_logger()


class UserService:
    """
    Бизнес-логика управления пользователями.

    Слой сервиса отвечает за:
    - Валидацию бизнес-правил
    - Координацию между репозиториями
    - Преобразование схем в модели и обратно
    """

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def get_user_with_profile(self, user_id: str) -> User:
        """
        Получение пользователя с профилем по ID.

        Args:
            user_id: UUID пользователя в виде строки

        Returns:
            User: Объект пользователя с загруженным профилем

        Raises:
            NotFoundError: Если пользователь не найден
        """
        from uuid import UUID

        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise NotFoundError() from e

        user = await self.user_repo.get_with_profile(user_uuid)
        if not user:
            raise NotFoundError()

        return user

    async def update_user_profile(
        self,
        user_id: str,
        user_update: UserUpdate,
    ) -> User:
        """
        Обновление профиля пользователя.

        Args:
            user_id: UUID пользователя в виде строки
            user_update: Данные для обновления

        Returns:
            User: Обновлённый объект пользователя с профилем

        Raises:
            NotFoundError: Если пользователь не найден
        """
        from uuid import UUID

        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise NotFoundError() from e

        user = await self.user_repo.get_with_profile(user_uuid)
        if not user:
            raise NotFoundError()

        update_data = user_update.model_dump(exclude_unset=True)

        if user.profile:
            for field, value in update_data.items():
                if hasattr(user.profile, field):
                    setattr(user.profile, field, value)
        else:
            logger.warning("Profile not found for user", user_id=user_id)

        await self.user_repo.db.commit()

        updated_user = await self.user_repo.get_with_profile(user_uuid)
        if not updated_user:
            raise NotFoundError()

        logger.info(
            "User profile updated",
            user_id=user_id,
            fields=list(update_data.keys()),
        )
        return updated_user

    async def change_password(
        self,
        user_id: str,
        password_request: PasswordChangeRequest,
    ) -> None:
        """
        Смена пароля пользователя.

        Args:
            user_id: UUID пользователя в виде строки
            password_request: Запрос со старым и новым паролем

        Raises:
            InvalidCredentialsError: Если старый пароль неверный
            NotFoundError: Если пользователь не найден
        """
        from uuid import UUID

        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise NotFoundError() from e

        user = await self.user_repo.get(user_uuid)
        if not user:
            raise NotFoundError()

        if not verify_password(password_request.old_password, user.hashed_password):
            raise InvalidCredentialsError()

        user.hashed_password = hash_password(password_request.new_password)
        await self.user_repo.db.commit()

        logger.info("Password changed successfully", user_id=user_id)

    async def create_curator(self, curator_data: CuratorCreate) -> User:
        """
        Создание куратора (только администратором).

        Args:
            curator_data: Данные для создания куратора

        Returns:
            User: Созданный объект куратора с профилем

        Raises:
            UserAlreadyExistsError: Если email уже занят
        """
        if await self.user_repo.email_exists(curator_data.email):
            raise UserAlreadyExistsError()

        new_curator = User(
            email=curator_data.email,
            hashed_password=hash_password(curator_data.password),
            role=UserRole.CURATOR,
            is_verified=True,
            is_active=True,
        )

        user = await self.user_repo.create_with_profile(
            user=new_curator,
            first_name=curator_data.first_name,
            last_name=curator_data.last_name,
        )

        logger.info(
            "Curator created by admin",
            curator_id=str(user.id),
            email=user.email,
        )
        return user

    async def verify_employer(self, employer_id: str, is_verified: bool) -> User:
        """
        Верификация работодателя куратором.

        Args:
            employer_id: UUID работодателя в виде строки
            is_verified: Статус верификации

        Returns:
            User: Обновлённый объект работодателя

        Raises:
            NotFoundError: Если работодатель не найден или ID некорректен
            PermissionDeniedError: Если пользователь не работодатель
        """
        from uuid import UUID

        try:
            employer_uuid = UUID(employer_id)
        except ValueError as e:
            raise NotFoundError() from e

        employer = await self.user_repo.get_with_profile(employer_uuid)
        if not employer:
            raise NotFoundError()

        if employer.role != UserRole.EMPLOYER:
            raise PermissionDeniedError(detail="User is not an employer")

        employer.is_verified = is_verified
        await self.user_repo.db.commit()
        await self.user_repo.db.refresh(employer)

        logger.info(
            "Employer verification status updated",
            employer_id=str(employer.id),
            is_verified=is_verified,
        )
        return employer
