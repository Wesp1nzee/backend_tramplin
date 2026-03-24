from src.core.config import settings
from src.core.security import hash_password
from src.db.session import SessionManager
from src.models.enums import UserRole
from src.models.user import Profile, User

DEFAULT_ADMIN_EMAIL = settings.DEFAULT_ADMIN_EMAIL
DEFAULT_ADMIN_PASSWORD = settings.DEFAULT_ADMIN_PASSWORD
DEFAULT_ADMIN_FIRST_NAME = "Администратор"
DEFAULT_ADMIN_LAST_NAME = "Платформы"


async def create_default_admin(session_manager: SessionManager) -> None:
    """
    Создает пользователя-администратора по умолчанию, если он ещё не существует.

    Согласно ТЗ: "По умолчанию в проекте уже должен быть как минимум один куратор,
    который называется администратор".

    Эта функция должна вызываться при старте приложения в lifespan.
    """
    if session_manager.engine is None:
        return

    async with session_manager.engine.begin() as conn:
        try:
            from sqlalchemy import insert, select

            result = await conn.execute(select(User).where(User.email == DEFAULT_ADMIN_EMAIL))
            existing_admin = result.fetchone()

            if existing_admin:
                return

            from datetime import UTC, datetime
            from uuid import uuid4

            admin_id = uuid4()
            now = datetime.now(UTC)

            await conn.execute(
                insert(User).values(
                    id=admin_id,
                    email=DEFAULT_ADMIN_EMAIL,
                    hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
                    role=UserRole.CURATOR,
                    is_active=True,
                    is_verified=True,
                    created_at=now,
                    updated_at=now,
                )
            )

            profile_id = uuid4()
            await conn.execute(
                insert(Profile).values(
                    id=profile_id,
                    user_id=admin_id,
                    first_name=DEFAULT_ADMIN_FIRST_NAME,
                    last_name=DEFAULT_ADMIN_LAST_NAME,
                    middle_name=None,
                    university=None,
                    graduation_year=None,
                    social_links={},
                    privacy_settings={
                        "public_profile": True,
                        "show_contacts": False,
                        "show_github": True,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )

            await conn.commit()
        except Exception:
            raise
