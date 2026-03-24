FROM python:3.14-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY uv.lock pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY ./src ./src
COPY ./migrations ./migrations
COPY alembic.ini ./
COPY ./scripts/start.sh /start.sh

RUN groupadd -r python && useradd -r -g python python && \
    chmod +x /start.sh && \
    chown -R python:python /app

USER python

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["/start.sh"]
