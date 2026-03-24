.PHONY: lint format typecheck security security-scan all run sync mm migrate rollback history current test install-hooks

# ─── Code Quality ──────────────────────────────────────────────────────────────

# Запуск линтера
lint:
	uv run ruff check . --fix

# Форматирование кода
format:
	uv run ruff format .

# Проверка типов
typecheck:
	uv run mypy .

# Проверка кода на уязвимости (Bandit)
security-bandit:
	uv run bandit -r src/ --skip B105,B106

# Аудит зависимостей на CVE (pip-audit)
security-audit:
	uv run pip-audit

# Запуск всех проверок безопасности
security: security-bandit security-audit

# Запуск всего: форматирование + линт + типы + безопасность
all: format lint typecheck security


# Запуск FastAPI в режиме разработки
run:
	uv run granian src.main:app --interface asgi --reload --reload-ignore-dirs 'logs'

# Запуск тестов
test:
	./scripts/run_tests.sh

# Синхронизация зависимостей
sync:
	uv sync --all-extras --dev

# Установка pre-commit хуков
install-hooks:
	uv run pre-commit install

# Создать новую миграцию
# Использование: make mm m="описание миграции"
mm:
	uv run alembic revision --autogenerate -m "$(m)"

# Применить все миграции
migrate:
	uv run alembic upgrade head

# Откатить последнюю миграцию на 1 шаг назад
rollback:
	uv run alembic downgrade -1

# Посмотреть историю миграций
history:
	uv run alembic history --verbose

# Посмотреть текущий статус
current:
	uv run alembic current

# Создать пустую миграцию
revision:
	uv run alembic revision -m "$(m)"

# Проверка перед коммитом (быстрая)
pre-commit: format lint security-bandit

# Проверка перед пушем (полная)
pre-push: all test
