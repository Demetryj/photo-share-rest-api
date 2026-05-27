"""Unit tests for role access service helpers."""

import pytest
from fastapi import HTTPException

from src.entity.user import Role, User
from src.services.role import RoleAccess


@pytest.mark.asyncio
async def test_role_access_allows_user_with_permitted_role() -> None:
    """Allow the request when the user's role is explicitly permitted."""

    access = RoleAccess([Role.admin, Role.user])
    user = User(id=1, role=Role.user)

    result = await access(request=None, user=user)

    assert result is None


@pytest.mark.asyncio
async def test_role_access_raises_403_for_disallowed_role() -> None:
    """Raise 403 when the user's role is not in the allowed list."""

    access = RoleAccess([Role.admin])
    user = User(id=2, role=Role.user)

    with pytest.raises(HTTPException) as exc_info:
        await access(request=None, user=user)

    assert exc_info.value.status_code == 403
