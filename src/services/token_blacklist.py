"""Redis-backed blacklist for revoked access tokens."""

from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
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

    def _decode_token_without_exp_verification(
        self, token: str
    ) -> dict[str, Any] | None:
        """Decode a JWT while ignoring expiration validation.

        This is used only to read technical claims such as ``exp`` and ``jti``
        when we need to revoke a token that may be close to expiration.
        """
        try:
            return jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.hash_algorithm],
                options={"verify_exp": False},
            )
        except JWTError:
            return None

    def _get_token_jti(self, token: str) -> str | None:
        """Extract the token ``jti`` claim or return ``None``."""
        payload = self._decode_token_without_exp_verification(token)
        if payload is None:
            return None

        jti = payload.get("jti")
        if not isinstance(jti, str) or not jti:
            return None

        return jti

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
        payload = self._decode_token_without_exp_verification(token)
        if payload is None:
            return 0

        exp = payload.get("exp")
        if exp is None:
            return 0

        now_ts = int(datetime.now(timezone.utc).timestamp())
        ttl = int(exp) - now_ts
        return max(ttl, 0)

    async def add_to_blacklist_access_token(self, token: str) -> None:
        """Put the current access token into Redis blacklist until it expires."""
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
