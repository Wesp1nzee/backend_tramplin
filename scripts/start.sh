#!/bin/bash
set -e

export UV_CACHE_DIR="/tmp/.cache/uv"

echo "Running migrations..."
uv run alembic upgrade head

echo "Starting server..."
exec uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8000
