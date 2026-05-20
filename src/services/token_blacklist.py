"""Redis-backed blacklist for revoked access tokens."""

import hashlib
from datetime import datetime, timezone

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

    def _build_token_hash(self, token: str) -> str:
        """Hash the token before storing it in Redis."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _build_key(self, token: str) -> str:
        """Build a namespaced Redis key for a revoked access token."""
        token_hash = self._build_token_hash(token)
        return f"{self._prefix}:{token_hash}"

    def get_token_ttl(self, token: str) -> int:
        """Return remaining token lifetime in seconds.

        If the token is invalid or already expired, return 0.
        """
        try:
            # We decode without expiration verification because logout/ban can be
            # called near the token boundary, and we only need the `exp` claim.
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.hash_algorithm],
                options={"verify_exp": False},
            )
        except JWTError:
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

        redis = await self.get_redis()
        key = self._build_key(token)

        # We only care that the key exists; the marker value itself is irrelevant.
        await redis.set(key, "1", ex=ttl)

    async def is_blacklisted(self, token: str) -> bool:
        """Return True when the token is already present in blacklist."""
        redis = await self.get_redis()
        key = self._build_key(token)
        return await redis.exists(key) == 1


token_blacklist_service = TokenBlacklistService()
