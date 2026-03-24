from uuid import UUID

from sqlalchemy import select

from src.core.exceptions import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    UserAlreadyExistsError,
)
from src.core.security import hash_password, verify_password
from src.models.enums import UserRole
from src.models.skill import ProfileSkill, Skill
from src.models.user import Profile, User
from src.repositories.user import UserRepository
from src.schemas.user import CuratorCreate, PasswordChangeRequest, UserUpdate


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
        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise NotFoundError() from e

        user = await self.user_repo.get_with_profile(user_uuid)
        if not user:
            raise NotFoundError()

        update_data = user_update.model_dump(exclude_unset=True)

        # Handle skills separately - they are stored in ProfileSkill relationship
        skills_data = update_data.pop("skills", None)

        if user.profile:
            for field, value in update_data.items():
                if hasattr(user.profile, field):
                    setattr(user.profile, field, value)

            # Handle skills update
            if skills_data is not None:
                await self._update_profile_skills(user.profile, skills_data)

        await self.user_repo.db.commit()

        # Clear session cache to ensure fresh data on next select
        self.user_repo.db.expire_all()

        # Explicitly reload with profile_skills to ensure they are loaded
        from sqlalchemy.orm import selectinload

        result = await self.user_repo.db.execute(
            select(User)
            .options(selectinload(User.profile).selectinload(Profile.profile_skills).selectinload(ProfileSkill.skill))
            .where(User.id == user_uuid)
        )
        updated_user = result.scalar_one_or_none()
        if not updated_user:
            raise NotFoundError()

        return updated_user

    async def _update_profile_skills(
        self,
        profile: Profile,
        skills: list[str],
    ) -> None:
        """
        Update profile skills by creating/deleting ProfileSkill relationships.

        Args:
            profile: Profile object to update
            skills: List of skill names as strings
        """
        # Get current skill names
        current_skill_names = {ps.skill.name for ps in profile.profile_skills}
        new_skill_names = set(skills)

        # Skills to remove
        skills_to_remove = current_skill_names - new_skill_names
        # Skills to add
        skills_to_add = new_skill_names - current_skill_names

        # Remove old skills using delete
        if skills_to_remove:
            # Get skill IDs to remove
            skills_to_remove_objs = [ps for ps in profile.profile_skills if ps.skill.name in skills_to_remove]
            for ps in skills_to_remove_objs:
                await self.user_repo.db.delete(ps)

        # Add new skills
        if skills_to_add:
            # Get or create skills
            result = await self.user_repo.db.execute(select(Skill).where(Skill.name.in_(skills_to_add)))
            existing_skills = result.scalars().all()
            existing_skill_map = {s.name: s for s in existing_skills}

            # Create missing skills
            skills_to_create = [s for s in skills_to_add if s not in existing_skill_map]
            if skills_to_create:
                for skill_name in skills_to_create:
                    new_skill = Skill(
                        name=skill_name,
                        slug=skill_name.lower().replace(" ", "-"),
                    )
                    self.user_repo.db.add(new_skill)

                # Flush to get the IDs for newly created skills
                await self.user_repo.db.flush()

                # Reload to get the newly created skills with IDs
                result = await self.user_repo.db.execute(select(Skill).where(Skill.name.in_(skills_to_create)))
                for skill in result.scalars().all():
                    existing_skill_map[skill.name] = skill

            # Create ProfileSkill relationships
            for skill_name in skills_to_add:
                skill = existing_skill_map[skill_name]
                profile_skill = ProfileSkill(
                    profile_id=profile.id,
                    skill_id=skill.id,
                    proficiency_level=1,  # Default level
                )
                self.user_repo.db.add(profile_skill)

            # Flush to ensure ProfileSkill records are written to DB
            await self.user_repo.db.flush()

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

        return employer
