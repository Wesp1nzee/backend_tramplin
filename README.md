# Tramplin API

Backend для экосистемы «Трамплин» — платформа для студентов и работодателей.

**Стек:** FastAPI, SQLAlchemy (async), Alembic, PostgreSQL (+PostGIS), Redis, RabbitMQ, uv

---

## 🚀 Быстрый старт

### Требования

- Python 3.14 (управляется через [`uv`](https://github.com/astral-sh/uv))
- Docker и Docker Compose

### Установка

```bash
# Клонировать репозиторий
git clone <repository-url> && cd backend_tramplin

# Синхронизировать зависимости
uv sync

# Создать файл окружения
cp .example.env .env
```

Отредактируйте `.env`, указав необходимые переменные (минимум — `SECRET_KEY` и параметры БД).

### Запуск через Docker Compose

```bash
docker-compose up -d
```

Сервер доступен на `http://localhost:8000`.

### Локальный запуск (без Docker)

```bash
# Запуск сервера разработки
make run

# Или напрямую
uv run granian src.main:app --interface asgi --reload
```

---

## 📚 Документация API

После запуска сервера:

| Эндпоинт | Описание |
|----------|----------|
| `http://localhost:8000/api/docs` | Swagger UI (автосгенерированная документация) |
| `http://localhost:8000/health` | Health check для Docker/K8s |

### Новые эндпоинты (MVP)

#### 🔒 Профиль и приватность

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| `GET` | `/api/v1/users/{user_id}` | Публичный профиль пользователя с учётом настроек приватности |
| `GET` | `/api/v1/users/applicants/search` | Поиск соискателей (EMPLOYER/CURATOR) |

**Приватность:**
- Если `public_profile=False`: имя, контакты и CV скрыты
- Если `show_contacts=False`: телефон и соцсети скрыты
- Владелец профиля видит все данные полностью

#### 📁 Загрузка файлов

| Метод | Эндпоинт | Описание | Auth |
|-------|----------|----------|------|
| `POST` | `/api/v1/uploads/cv` | Загрузка резюме (PDF, макс. 5MB) | APPLICANT |
| `POST` | `/api/v1/uploads/media` | Загрузка медиа (JPG/PNG/WEBP/MP4, макс. 10MB) | EMPLOYER/CURATOR |

**Возвращает:**
```json
{
  "url": "http://localhost:8000/static/uploads/cvs/uuid.pdf",
  "filename": "uuid.pdf",
  "file_type": "application/pdf",
  "file_size": 123456
}
```

#### 💡 Рекомендации

| Метод | Эндпоинт | Описание | Auth |
|-------|----------|----------|------|
| `POST` | `/api/v1/recommendations` | Рекомендовать вакансию контакту | APPLICANT |
| `GET` | `/api/v1/recommendations/sent` | Список отправленных рекомендаций | APPLICANT |
| `GET` | `/api/v1/recommendations/received` | Список полученных рекомендаций | APPLICANT |
| `PATCH` | `/api/v1/recommendations/{id}/read` | Отметить рекомендацию как прочитанную | APPLICANT |

**Требования:**
- Между отправителем и получателем должна быть связь `Contact` со статусом `ACCEPTED`
- Вакансия должна быть активной (`ACTIVE`)
- Получатель должен быть соискателем (`APPLICANT`)
- Нельзя рекомендовать самому себе

---

## 🛠 Разработка

### Основные команды

```bash
# Запуск линтера
make lint

# Форматирование кода
make format

# Проверка типов
make typecheck

# Запуск всех проверок
make all

# Запуск тестов
make test

# Синхронизация зависимостей
make sync
```

### Работа с миграциями

```bash
# Создать миграцию (автоматически)
make mm m="описание миграции"

# Применить все миграции
make migrate

# Откатить последнюю миграцию
make rollback

# История миграций
make history

# Текущая миграция
make current
```

---

## 🧪 Тестирование

```bash
# Запустить все тесты
uv run pytest tests/ -v

# Запустить с покрытием
uv run pytest tests/ -v --cov=src

# Запустить конкретный тест
uv run pytest tests/unit/test_auth.py -v
```

---

## 📁 Структура проекта

```
src/
├── main.py              # Точка входа, lifespan, middleware
├── api/                 # HTTP слой (endpoints, deps)
│   └── v1/
│       └── endpoints/   # Роутеры по доменам (auth, users, etc.)
├── core/                # Конфигурация, безопасность, исключения
├── db/                  # Сессии БД, базовые классы моделей
├── models/              # SQLAlchemy ORM модели
├── schemas/             # Pydantic схемы (DTO)
├── repositories/        # Слой доступа к данным (Repository pattern)
└── services/            # Бизнес-логика (Use Cases)
```

Полное описание архитектуры — см. [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## 🔗 Ссылки

- [Архитектура](./ARCHITECTURE.md)
- [ADR записи](./docs/adr/)
