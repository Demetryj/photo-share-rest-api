"""Shared Redis client factories for the application."""

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from src.config.settings import settings


def use_redis_ssl() -> bool:
    """Return True when Redis connection should use TLS/SSL. (local/prod)"""

    return settings.REDIS_URL.startswith("rediss://")


def get_sync_redis_client() -> Redis:
    """Return a sync Redis client for libraries that require sync access."""

    return Redis(
        host=settings.REDIS_DOMAIN,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        ssl=use_redis_ssl(),
    )


def get_async_redis_client() -> AsyncRedis:
    """Return an async Redis client for application async services."""

    return AsyncRedis(
        host=settings.REDIS_DOMAIN,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        ssl=use_redis_ssl(),
    )
