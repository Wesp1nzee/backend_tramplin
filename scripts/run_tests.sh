#!/bin/bash

docker-compose -f docker-compose.test.yml up -d test_db

export DATABASE_URL="postgresql+asyncpg://test_user:test_password@localhost:5433/test_tramplin?ssl=disable"

echo "Waiting for DB on localhost:5433..."
until docker run --rm --network host postgres:17-alpine pg_isready -h localhost -p 5433 -U test_user; do
  echo "Database is unavailable - sleeping"
  sleep 1
done

echo "DB is ready!"


export ENVIRONMENT=test
pytest -v -s tests/

docker-compose -f docker-compose.test.yml down
