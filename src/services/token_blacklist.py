"""Redis-backed blacklist for revoked access tokens."""

from datetime import datetime, timezone

from redis.asyncio import Redis

from src.config.settings import settings


class TokenBlacklistService:
    """Store revoked access tokens in Redis until they expire naturally."""

    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._prefix = "blacklist:access"

    async def get_redis(self) -> Redis:
        """Return a cached Redis client, creating it on first use."""

        if self._redis is None:
            self._redis = Redis(
                host=settings.REDIS_DOMAIN,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        """Close Redis connection on application shutdown."""

        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    def _get_token_jti(self, token: str) -> str | None:
        """Extract the token ``jti`` claim or return ``None``."""

        from src.services.auth import auth_service

        return auth_service.get_token_jti(token)

    def _build_key(self, token: str) -> str | None:
        """Build a namespaced Redis key for a revoked access token."""

        jti = self._get_token_jti(token)
        if jti is None:
            return None
        return f"{self._prefix}:{jti}"

    def get_token_ttl(self, token: str) -> int:
        """Return remaining token lifetime in seconds.

        If the token is invalid or already expired, return 0.
        """
        from src.services.auth import auth_service

        exp = auth_service.get_token_exp(token)
        if exp is None:
            return 0

        now_ts = int(datetime.now(timezone.utc).timestamp())
        ttl = exp - now_ts
        return max(ttl, 0)

    async def add_access_token_jti_to_blacklist(
        self, token: str
    ) -> None:
        """Add the current access-token JTI to the Redis blacklist for the rest of the token lifetime."""

        ttl = self.get_token_ttl(token)
        if ttl <= 0:
            return

        key = self._build_key(token)
        if key is None:
            return

        redis = await self.get_redis()

        # We only care that the key exists; the marker value itself is irrelevant.
        await redis.set(key, "1", ex=ttl)

    async def is_blacklisted(self, token: str) -> bool:
        """Return True when the token is already present in blacklist."""

        key = self._build_key(token)
        if key is None:
            return False

        redis = await self.get_redis()
        return await redis.exists(key) == 1


token_blacklist_service = TokenBlacklistService()
