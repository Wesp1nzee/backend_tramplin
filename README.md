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

#### ⭐ Избранное (Favorites)

| Метод | Эндпоинт | Описание | Auth |
|-------|----------|----------|------|
| `POST` | `/api/v1/favorites/sync` | Синхронизация localStorage с БД при логине | APPLICANT |
| `GET` | `/api/v1/favorites/opportunities` | Список избранных вакансий | APPLICANT |
| `GET` | `/api/v1/favorites/companies` | Список избранных компаний | APPLICANT |
| `POST` | `/api/v1/favorites/opportunities/{id}` | Добавить вакансию в избранное | APPLICANT |
| `DELETE` | `/api/v1/favorites/opportunities/{id}` | Удалить вакансию из избранного | APPLICANT |
| `POST` | `/api/v1/favorites/companies/{id}` | Добавить компанию в избранное | APPLICANT |
| `DELETE` | `/api/v1/favorites/companies/{id}` | Удалить компанию из избранного | APPLICANT |

**Синхронизация:**
- Неавторизованные пользователи хранят избранное в localStorage
- При логине фронтенд отправляет `POST /favorites/sync` с `{opportunity_ids, company_ids}`
- Бэкенд объединяет с БД без дубликатов, возвращает итоговый список

**Избранные компании на карте:**
- Маркеры компаний из избранного помечаются `is_favorite_company: true`
- Фронтенд может отображать их отдельным цветом/иконкой

#### 🎓 Мероприятия (Events)

| Метод | Эндпоинт | Описание | Auth |
|-------|----------|----------|------|
| `GET` | `/api/v1/events/{id}/info` | Информация о мероприятии | Любой авторизованный |
| `POST` | `/api/v1/events/{id}/register` | Регистрация на мероприятие | APPLICANT |
| `DELETE` | `/api/v1/events/{id}/register` | Отмена регистрации | APPLICANT |
| `GET` | `/api/v1/events/{id}/participants` | Список участников | EMPLOYER/CURATOR |
| `POST` | `/api/v1/events/{id}/check-in` | Отметка присутствия по коду | EMPLOYER/CURATOR |

**Логика регистрации:**
- Если есть места → статус `confirmed`, генерируется `check_in_code`
- Если мест нет → статус `waitlist` (лист ожидания)
- При отмене участник из waitlist автоматически продвигается
- Работодатель получает уведомление о каждой регистрации

**Check-in:**
- Уникальный код (8 символов) для офлайн-верификации
- Работодатель сканирует QR или вводит код вручную

#### 🔍 Поиск соискателей (Applicants)

| Метод | Эндпоинт | Описание | Auth |
|-------|----------|----------|------|
| `GET` | `/api/v1/applicants/search` | Поиск по навыкам, университету, году | EMPLOYER/CURATOR |
| `GET` | `/api/v1/applicants/{profile_id}` | Детальный профиль | EMPLOYER/CURATOR |
| `POST` | `/api/v1/applicants/{profile_id}/contact` | Запрос в контакты | EMPLOYER |

**Фильтры поиска:**
- `skills` — список навыков через запятую (Python,FastAPI,PostgreSQL)
- `university` — часть названия университета
- `graduation_year` — год выпуска
- `city` — город

**Приватность:**
- В поиске участвуют только `public_profile=true`
- Скрытые профили не отображаются в результатах
- Детальный профиль применяет настройки приватности

**Сортировка:**
- По навыкам → по релевантности (количество совпадений)
- Без навыков → по году выпуска (recent first)

#### 🛡 Модерация вакансий (Curator Moderation)

| Метод | Эндпоинт | Описание | Auth |
|-------|----------|----------|------|
| `GET` | `/api/v1/opportunities/moderation/pending` | Список на модерации | CURATOR |
| `GET` | `/api/v1/opportunities/moderation/{id}` | Детали для проверки | CURATOR |
| `POST` | `/api/v1/opportunities/moderation/{id}/review` | Одобрить/отклонить | CURATOR |

**Статусы модерации:**
- `DRAFT` → черновик (создание/редактирование)
- `PLANNED` → отправлено на модерацию
- `ACTIVE` → одобрено и опубликовано
- `REJECTED` → отклонено (возврат в DRAFT)

**Уведомления:**
- Работодатель получает `NotificationType.SYSTEM` о результате
- Комментарий куратора виден работодателю

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
