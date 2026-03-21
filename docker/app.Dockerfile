FROM python:3.14-slim-bookworm

# Устанавливаем uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Копируем файлы зависимостей
COPY uv.lock pyproject.toml ./

# Устанавливаем зависимости
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Копируем исходный код
COPY ./src ./src
COPY ./alembic ./alembic
COPY alembic.ini ./

# Создаём пользователя
RUN groupadd -r python && useradd -r -g python python
RUN chown -R python:python /app
USER python

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "src.main:app"]