# Архитектура Tramplin API

## Обзор

Проект использует **слоистую архитектуру** (Layered Architecture) с явным разделением ответственности между компонентами.

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                     │
│  endpoints/ ─→ deps.py ─→ schemas (Request/Response DTOs)   │
└─────────────────────────────────────────────────────────────┘
                            ↓ Depends()
┌─────────────────────────────────────────────────────────────┐
│                   Service Layer (Business Logic)             │
│  AuthService, UserService, etc. ─→ domain logic, validation  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                Repository Layer (Data Access)                │
│  UserRepository, BaseRepository[T] ─→ SQL queries, ORM       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer (SQLAlchemy)                │
│  Models (User, Profile) ─→ Tables, Relationships             │
└─────────────────────────────────────────────────────────────┘
```

---

## Правила импортов между слоями

| Слой | Может импортировать | Запрещено |
|------|---------------------|-----------|
| **API** (`api/v1/endpoints/*`) | `services`, `schemas`, `deps`, `core` | `repositories`, `models` |
| **Services** (`services/*`) | `repositories`, `schemas`, `models` (type hints), `core` | `api`, `endpoints` |
| **Repositories** (`repositories/*`) | `models`, `db`, `core` | `services`, `api`, `schemas` |
| **Models** (`models/*`) | `db` (Base, mixins) | Всё остальное |

**Пример нарушения:**
```python
# ❌ НЕЛЬЗЯ: repository импортирует сервис
from src.services.auth import AuthService

# ✅ МОЖНО: service импортирует repository
from src.repositories.user import UserRepository
```

---

## Dependency Injection (`deps.py`)

Все зависимости объявлены в [`src/api/v1/deps.py`](./src/api/v1/deps.py).

### Базовые зависимости

```python
# Сессия БД (async)
def get_db() -> AsyncGenerator[AsyncSession]

# Репозиторий пользователей
def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository

# Сервис аутентификации
def get_auth_service(user_repo: UserRepository = Depends(get_user_repository)) -> AuthService
```

### Аутентификация и авторизация

```python
# Текущий пользователь из JWT
async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(reusable_oauth2),
) -> User

# Верифицированный пользователь
async def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User

# RBAC: проверка роли
class RoleChecker:
    def __init__(self, allowed_roles: list[UserRole])
    def __call__(self, user: User = Depends(get_current_user)) -> User
```

**Пример использования в endpoint:**

```python
from fastapi import APIRouter, Depends

from src.api.v1.deps import get_current_user, RoleChecker
from src.models.enums import UserRole
from src.models.user import User

router = APIRouter()

# Только для кураторов
require_curator = RoleChecker([UserRole.CURATOR])

@router.delete("/users/{user_id}", dependencies=[Depends(require_curator)])
async def delete_user(user_id: uuid.UUID):
    ...

# Любой авторизованный пользователь
@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
```

---

## Жизненный цикл запроса

На примере `POST /api/v1/auth/login`:

```
1. Middleware (CORS, exception handlers)
         ↓
2. FastAPI Router (api/v1/endpoints/auth.py)
         ↓
3. Dependency Injection:
   - get_db() → AsyncSession
   - get_user_repository() → UserRepository
   - get_auth_service() → AuthService
         ↓
4. Endpoint: login(form_data, auth_service)
         ↓
5. Service Layer: AuthService.authenticate(email, password)
   - Проверка учётных данных
   - Логирование
         ↓
6. Repository Layer: UserRepository.get_by_email_with_profile(email)
   - SQL запрос через SQLAlchemy
         ↓
7. Database: PostgreSQL (asyncpg)
         ↓
8. Response: AuthResponse (tokens + user data)
```

**Диаграмма последовательности:**

```
Client          API            Service        Repository      DB
  │              │                │               │            │
  │──POST /login─▶│                │               │            │
  │              │──depends──────▶│               │            │
  │              │                │──authenticate─▶│            │
  │              │                │               │──SELECT────▶│
  │              │                │               │◀────────────│
  │              │                │◀──────────────│            │
  │              │◀───────────────│               │            │
  │◀─────────────│                │               │            │
```

---

## Ключевые компоненты

### SessionManager (`src/db/session.py`)

Управление пулом соединений с БД:

```python
class SessionManager:
    def init(self, db_url: str) -> None:
        # Создаёт AsyncEngine с настройками pool_size=20, max_overflow=10
        ...

    async def close(self) -> None:
        # Закрывает все соединения при остановке приложения
        ...

    async def check_health(self) -> bool:
        # Health check для /health endpoint
        ...
```

**Использование в lifespan:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    session_manager.init(settings.DATABASE_URL)
    yield
    await session_manager.close()
```

### BaseRepository (`src/repositories/base.py`)

Generic-репозиторий с CRUD-операциями:

```python
class BaseRepository[ModelType: Base]:
    model: type[ModelType]

    async def get(self, obj_id: UUID) -> ModelType | None
    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]
    async def exists(self, obj_id: UUID) -> bool
    async def delete(self, obj: ModelType) -> None
```

**Наследники добавляют специфичные запросы:**
```python
class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None
    async def get_by_email_with_profile(self, email: str) -> User | None
    async def email_exists(self, email: str) -> bool
    async def create_with_profile(...) -> User
```

### AppError (`src/core/exceptions.py`)

Базовый класс для доменных исключений:

```python
class AppError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Internal server error"

# Примеры наследников
class UserAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "User with this email already exists"

class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Invalid email or password"
```

**Глобальный обработчик:**
```python
@app.exception_handler(AppError)
async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
```

**Использование в сервисе:**
```python
async def register_new_user(self, user_in: UserCreate) -> AuthResponse:
    if await self.user_repo.email_exists(user_in.email):
        raise UserAlreadyExistsError()  # → 409 Conflict
    ...
```

---

## Модели данных

### User и Profile (`src/models/user.py`)

```python
class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    role: Mapped[UserRole]  # StrEnum: applicant, employer, curator
    is_active: Mapped[bool]
    is_verified: Mapped[bool]
    profile: Mapped[Profile]  # 1:1 relationship

class Profile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profiles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    university: Mapped[str | None]
    skills: Mapped[list[str]]  # JSONB
    privacy_settings: Mapped[dict[str, bool]]  # JSONB
```

### Схемы (Pydantic DTO)

```python
# src/schemas/user.py
class UserCreate(SchemaBase):
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.APPLICANT
    first_name: str
    last_name: str

class AuthResponse(SchemaBase):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
```

---

## Конфигурация

[`src/core/config.py`](./src/core/config.py) использует `pydantic-settings`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    PROJECT_NAME: str = "Tramplin API"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str | PostgresDsn  # вычисляется из компонентов

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
```

**Использование:**
```python
from src.core.config import settings

settings.DEBUG  # True/False
settings.DATABASE_URL  # "postgresql+asyncpg://..."
settings.cors_origins_list  # распарсенный список из CORS_ORIGINS
```
