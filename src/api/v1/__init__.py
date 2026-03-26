from fastapi import APIRouter

from src.api.v1.endpoints.auth import router as auth_router
from src.api.v1.endpoints.glossary import router as glossary_router

# Агрегирующий роутер для всей версии v1.
# При добавлении новых модулей
#
# Пример расширения:
#   from src.api.v1.endpoints.users import router as users_router
#   from src.api.v1.endpoints.vacancies import router as vacancies_router
#   v1_router.include_router(users_router)
#   v1_router.include_router(vacancies_router)

v1_router = APIRouter()
v1_router.include_router(auth_router)
v1_router.include_router(glossary_router)
