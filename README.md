
### 📂 Full Project Architecture

```text
tramplin-backend/
├── .github/workflows/       # CI/CD пайплайны (test, lint, deploy)
├── docker/                  # Конфигурации окружений
│   ├── app.Dockerfile       # Multi-stage build (uv-based)
│   ├── postgis.conf         # Тюнинг PostgreSQL под Highload
│   └── valkey.conf          # Конфиг кэша
├── scripts/                 # Утилиты для миграций и инициализации БД
├── tests/                   # Пирамида тестирования
│   ├── unit/                # Тесты сервисов и логики
│   ├── integration/         # Тесты репозиториев и БД
│   └── e2e/                 # Тесты API эндпоинтов (через TestClient)
│
├── src/                     # Основной код приложения
│   ├── main.py              # Точка входа, lifespan, подключение роутеров
│   │
│   ├── api/                 # Слой интерфейсов (Delivery Layer)
│   │   ├── deps.py          # Инъекция зависимостей (get_db, get_user)
│   │   └── v1/
│   │       ├── auth.py      # Регистрация и JWT (соискатель/работодатель)
│   │       ├── vacancies.py # Поиск, карта, фильтрация
│   │       ├── profile.py   # Личные кабинеты и настройки приватности
│   │       ├── company.py   # Управление карточками и верификация
│   │       ├── social.py    # Нетворкинг и контакты
│   │       └── curator.py   # Админка и модерация (Curator)
│   │
│   ├── core/                # Глобальные настройки и безопасность
│   │   ├── config.py        # pydantic-settings (env vars)
│   │   ├── security.py      # Хеширование, логика токенов
│   │   ├── exceptions.py    # Глобальные обработчики ошибок
│   │   └── logging.py       # Конфиг structlog (JSON для ELK/Loki)
│   │
│   ├── db/                  # Инфраструктурный слой БД
│   │   ├── session.py       # Настройка AsyncSession (SQLAlchemy + asyncpg)
│   │   ├── base.py          # DeclarativeBase, Mixins (Timestamp, Tenant)
│   │   └── repositories/    # Паттерн Repository (инкапсуляция SQL)
│   │       ├── base.py      # GenericRepository[T]
│   │       ├── user_repo.py
│   │       ├── vacancy_repo.py # Гео-запросы через PostGIS
│   │       └── company_repo.py
│   │
│   ├── models/              # SQLAlchemy ORM модели (Domain Entities)
│   │   ├── user.py          # User, Profile 
│   │   ├── company.py       # Company, VerificationData
│   │   ├── vacancy.py       # Vacancy, Tag, Location
│   │   └── interaction.py   # Application, Connection, Favorite
│   │
│   ├── schemas/             # Pydantic модели (Data Transfer Objects)
│   │   ├── common.py        # Пагинация, гео-координаты, базовые типы
│   │   ├── user.py          # Регистрация, профиль, приватность
│   │   ├── vacancy.py       # Карточка, превью, фильтры
│   │   └── company.py       # Данные компании, верификация
│   │
│   ├── services/            # Слой бизнес-логики (Use Cases)
│   │   ├── auth_service.py  # Логика входа и ролей
│   │   ├── geo_service.py   # Работа с картой и кластеризацией
│   │   ├── verify_service.py # Логика верификации работодателей
│   │   ├── vacancy_service.py # Обработка вакансий и тегов
│   │   └── social_service.py # Логика нетворкинга и рекомендаций
│   │
│   ├── workers/             # Фоновые задачи (FastStream / Celery)
│   │   ├── email_tasks.py   # Уведомления об откликах, верификация
│   │   └── report_tasks.py  # Генерация отчетов для кураторов
│   │
│   └── utils/               # Вспомогательные модули
│       ├── cache.py         # Обертки для Redis (кэш поиска)
│       └── storage.py       # Интеграция с S3 для медиа (фото офисов)
│
├── alembic/                 # Миграции базы данных
├── .env.example             # Шаблон переменных окружения
├── docker-compose.yml       # Оркестрация локального окружения
└── pyproject.toml           # Конфиг uv, ruff, mypy, pytest
```
