# Архитектура Tramplin API

## Обзор

Проект использует **слоистую архитектуру** (Layered Architecture) с явным разделением ответственности между компонентами.

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                    │
│  endpoints/ ─→ deps.py ─→ schemas (Request/Response DTOs)   │
│  ─→ Exception Handlers ─→ Middleware                        │
└─────────────────────────────────────────────────────────────┘
                            ↓ Depends()
┌─────────────────────────────────────────────────────────────┐
│                   Service Layer (Business Logic)            │
│  AuthService, UserService, etc. ─→ domain logic, validation │
│  ─→ raise DomainError (AppError наследники)                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                Repository Layer (Data Access)               │
│  UserRepository, BaseRepository[T] ─→ SQL queries, ORM      │
│  ─→ Проброс SQLAlchemy ошибок или RepositoryError           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer (SQLAlchemy)               │
│  Models (User, Profile) ─→ Tables, Relationships            │
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
   - raise InvalidCredentialsError (при ошибке)
         ↓
6. Repository Layer: UserRepository.get_by_email_with_profile(email)
   - SQL запрос через SQLAlchemy
   - Проброс SQLAlchemyError (при ошибке БД)
         ↓
7. Database: PostgreSQL (asyncpg)
         ↓
8. Exception Handler (если exception)
         ↓
9. Response: AuthResponse или Error JSON
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

---

## Обработка исключений (Exception Handling)

### Иерархия исключений (`src/core/exceptions.py`)

Все доменные исключения наследуются от `AppError` и содержат:
- `status_code` — HTTP статус ответа
- `detail` — Человекочитаемое сообщение
- `error_code` — Машинный код для фронтенд-логики

```python
class AppError(Exception):
    """Базовый класс для всех доменных исключений"""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Internal server error"
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


# ─── Authentication Errors (401, 403) ───
class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "AUTHENTICATION_FAILED"

class InvalidCredentialsError(AuthenticationError):
    detail = "Invalid email or password"

class InvalidTokenError(AuthenticationError):
    detail = "Invalid or expired token"

class UserNotActiveError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "User account is deactivated"
    error_code = "USER_NOT_ACTIVE"

class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "Not enough permissions"
    error_code = "PERMISSION_DENIED"


# ─── User Errors (400, 404, 409) ───
class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"
    error_code = "NOT_FOUND"

class UserAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "User with this email already exists"
    error_code = "USER_ALREADY_EXISTS"


# ─── Repository/Database Errors ───
class RepositoryError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "REPOSITORY_ERROR"
    detail = "Database operation failed"
```

### Глобальные обработчики исключений

Регистрируются в [`src/main.py`](./src/main.py) через `setup_exception_handlers(app)`:

```python
# src/core/exceptions.py

def setup_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(AppError)
    async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
        """Обработчик доменных исключений"""
        # Логирование по уровню важности
        if exc.status_code >= 500:
            logger.error(f"Server error: {exc.error_code}", detail=exc.detail)
        else:
            logger.warning(f"Client error: {exc.error_code}", detail=exc.detail)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.detail,
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """Обработчик валидации Pydantic"""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": exc.errors()
                }
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Fallback для необработанных исключений"""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error"
                }
            }
        )
```

### Где и как выбрасывать исключения

| Слой | Что делает | Пример |
|------|-----------|--------|
| **Repository** | Пробрасывает SQLAlchemy ошибки или оборачивает в `RepositoryError` | `raise RepositoryError()` при catch SQLAlchemyError |
| **Service** | **Основное место** для бизнес-исключений | `raise UserAlreadyExistsError()` |
| **API** | Валидация входных данных, `HTTPException` | `raise HTTPException(status_code=400)` |

**Пример использования в сервисе:**

```python
# src/services/auth.py

async def register_new_user(self, user_in: UserCreate) -> AuthResponse:
    if await self.user_repo.email_exists(user_in.email):
        raise UserAlreadyExistsError()  # → 409 Conflict

    # ... создание пользователя
    return AuthResponse(...)

async def authenticate(self, email: str, password: str) -> AuthResponse:
    user = await self.user_repo.get_by_email_with_profile(email)

    if not user or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError()  # → 401 Unauthorized

    if not user.is_active:
        raise UserNotActiveError()  # → 403 Forbidden

    return AuthResponse(...)
```

**Пример обработки в repository:**

```python
# src/repositories/base.py

from sqlalchemy.exc import SQLAlchemyError

async def get(self, obj_id: UUID) -> ModelType | None:
    try:
        return await self.db.get(self.model, obj_id)
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise RepositoryError() from e
    # ← Не ловим молча, пробрасываем выше
```

### Формат ответа при ошибке

```json
// ✅ Успешный ответ
{
    "access_token": "...",
    "refresh_token": "...",
    "token_type": "bearer",
    "user": {...}
}

// ❌ Ошибка (AppError)
{
    "error": {
        "code": "USER_ALREADY_EXISTS",
        "message": "User with this email already exists"
    }
}

// ❌ Ошибка валидации (422)
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Request validation failed",
        "details": [...]
    }
}
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

---

## Best Practices: Исключения

### ✅ DO (Правильно)

```python
# 1. Выбрасывать исключения в Service Layer
async def register(self, user_in: UserCreate):
    if await self.repo.email_exists(user_in.email):
        raise UserAlreadyExistsError()

# 2. Логировать в exception handlers
@app.exception_handler(AppError)
async def handler(request, exc):
    logger.warning(f"{exc.error_code}: {exc.detail}")
    return JSONResponse(...)

# 3. Использовать error_code для фронтенда
raise InvalidCredentialsError()  # → error_code: "AUTHENTICATION_FAILED"

# 4. Пробрасывать ошибки БД из repository
async def get(self, id: UUID):
    return await self.db.get(self.model, id)  # ← SQLAlchemyError пробрасывается
```

### ❌ DON'T (Неправильно)

```python
# 1. Не ловить исключения молча в repository
async def get(self, id: UUID):
    try:
        return await self.db.get(self.model, id)
    except:
        return None  # ← Скрываем ошибку!

# 2. Не использовать HTTPException в сервисе
async def register(self, user_in: UserCreate):
    raise HTTPException(409, "Exists")  # ← Нарушает слоистость!

# 3. Не возвращать detail из БД клиенту
except SQLAlchemyError as e:
    raise AppError(detail=str(e))  # ← Утечка информации!

# 4. Не создавать исключения в endpoint
@router.post("/register")
async def register(user: UserCreate):
    if exists:
        raise AppError()  # ← Логика должна быть в сервисе!
```

---

## Структура проекта (exceptions)

```
src/
├── core/
│   ├── exceptions.py          # ← Все исключения + handlers
│   ├── config.py
│   └── security.py
├── api/
│   └── v1/
│       ├── endpoints/
│       ├── deps.py
│       └── app.py
├── services/
│   ├── auth.py                # ← raise DomainError
│   └── user.py
├── repositories/
│   ├── base.py                # ← Проброс или RepositoryError
│   └── user.py
└── main.py                    # ← setup_exception_handlers(app)
```

**Главное правило:** Исключения определяются в `core`, выбрасываются в `service`, обрабатываются в `api`. Repository только пробрасывает или оборачивает в `RepositoryError`.
