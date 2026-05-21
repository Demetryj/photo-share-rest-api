"""Role-based access control dependencies for FastAPI routes."""

from fastapi import Depends, Request, status

from src.config.messages import HTTPStatusMessages
from src.entity.user import Role, User
from src.helpers.create_exception import create_exception
from src.services.auth import auth_service


class RoleAccess:
    """FastAPI dependency that restricts route access by user role.

    Instances of this class are used as route dependencies. The dependency
    receives the current authenticated user and checks whether the user's role
    is included in the configured list of allowed roles.
    """

    def __init__(self, allowed_roles: list[Role]):
        """Initialize role-based access rules."""
        self.allowed_roles = allowed_roles

    async def __call__(
        self,
        request: Request,
        user: User = Depends(auth_service.get_current_user),
    ):
        """Validate that the current user has one of the allowed roles."""

        if user.role not in self.allowed_roles:
            create_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                message=HTTPStatusMessages.operation_forbidden.value,
            )


# Reusable RBAC dependency for read endpoints; allows admin/moderator/user roles.
staff_only = RoleAccess([Role.admin, Role.moderator])
admin_only = RoleAccess([Role.admin])
authenticated_users = RoleAccess(
    [Role.admin, Role.moderator, Role.user]
)
admin_and_user_access = RoleAccess([Role.admin, Role.user])
