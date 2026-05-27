"""Unit tests for token blacklist service helpers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from src.services.token_blacklist import TokenBlacklistService


def test_get_token_ttl_returns_zero_when_exp_claim_is_missing() -> (
    None
):
    """Return zero when the token has no readable expiration timestamp."""

    service = TokenBlacklistService()
    auth_service_mock = Mock()
    auth_service_mock.get_token_exp.return_value = None
    service._get_auth_service = Mock(return_value=auth_service_mock)

    ttl = service.get_token_ttl("token")

    assert ttl == 0


def test_get_token_ttl_returns_remaining_lifetime_in_seconds() -> (
    None
):
    """Return the positive remaining lifetime for a not-yet-expired token."""

    service = TokenBlacklistService()
    future_exp = int(datetime.now(timezone.utc).timestamp()) + 60
    auth_service_mock = Mock()
    auth_service_mock.get_token_exp.return_value = future_exp
    service._get_auth_service = Mock(return_value=auth_service_mock)

    ttl = service.get_token_ttl("token")

    assert 1 <= ttl <= 60


@pytest.mark.asyncio
async def test_add_access_token_jti_to_blacklist_sets_redis_key_with_ttl() -> (
    None
):
    """Store the blacklist marker in Redis when the token is still active."""

    service = TokenBlacklistService()
    redis_mock = AsyncMock()
    service.get_token_ttl = Mock(return_value=45)
    service._build_key = Mock(
        return_value="blacklist:access:test-jti"
    )
    service.get_redis = AsyncMock(return_value=redis_mock)

    await service.add_access_token_jti_to_blacklist("token")

    redis_mock.set.assert_awaited_once_with(
        "blacklist:access:test-jti",
        "1",
        ex=45,
    )


@pytest.mark.asyncio
async def test_is_blacklisted_returns_false_when_token_has_no_blacklist_key() -> (
    None
):
    """Return False when the token cannot be mapped to a blacklist key."""

    service = TokenBlacklistService()
    service._build_key = Mock(return_value=None)

    result = await service.is_blacklisted("token")

    assert result is False


@pytest.mark.asyncio
async def test_is_blacklisted_returns_true_when_redis_contains_key() -> (
    None
):
    """Return True when Redis reports an existing blacklist key."""

    service = TokenBlacklistService()
    redis_mock = AsyncMock()
    redis_mock.exists.return_value = 1
    service._build_key = Mock(
        return_value="blacklist:access:test-jti"
    )
    service.get_redis = AsyncMock(return_value=redis_mock)

    result = await service.is_blacklisted("token")

    redis_mock.exists.assert_awaited_once_with(
        "blacklist:access:test-jti"
    )
    assert result is True
