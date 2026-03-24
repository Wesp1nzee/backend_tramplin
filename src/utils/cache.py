import redis.asyncio as redis


class TokenBlacklist:
    """
    Менеджер blacklist для JWT токенов.
    Использует Redis для хранения отозванных токенов до момента их истечения.
    """

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._prefix = "blacklist:token:"

    async def connect(self, redis_url: str) -> None:
        """Подключение к Redis."""
        self._redis = redis.from_url(redis_url, decode_responses=True)
        try:
            await self._redis.ping()  # type: ignore[misc]
        except Exception:
            raise

    async def disconnect(self) -> None:
        """Отключение от Redis."""
        if self._redis:
            await self._redis.close()

    async def add_token(self, token: str, expires_in_seconds: int) -> None:
        """
        Добавляет токен в blacklist.

        Args:
            token: JWT токен для добавления в blacklist
            expires_in_seconds: Время жизни токена в секундах (TTL)
        """
        if not self._redis:
            return

        key = f"{self._prefix}{token}"
        await self._redis.setex(key, expires_in_seconds, "1")

    async def is_blacklisted(self, token: str) -> bool:
        """
        Проверяет наличие токена в blacklist.

        Args:
            token: JWT токен для проверки

        Returns:
            True если токен в blacklist, False иначе
        """
        if not self._redis:
            return False

        key = f"{self._prefix}{token}"
        exists = await self._redis.exists(key)
        return bool(exists)

    async def check_health(self) -> bool:
        """Проверка доступности Redis."""
        if not self._redis:
            return False

        try:
            await self._redis.ping()  # type: ignore[misc]
            return True
        except Exception:
            return False


token_blacklist = TokenBlacklist()
