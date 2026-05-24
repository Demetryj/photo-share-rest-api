"""FastAPI routes for user authentication and email confirmation flows."""

from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse

# from fastapi.responses import  RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import rate_limiters
from src.config.messages import EmailMessages, HTTPStatusMessages
from src.config.settings import settings
from src.database.db import get_db
from src.entity.user import User
from src.helpers.create_exception import create_exception
from src.repository import auth as repository_auth
from src.repository import user as repository_user
from src.schemas.auth import (
    MessageResponseSchema,
    RequestEmail,
    ResetPasswordRequestSchema,
    SignInResponse,
)
from src.schemas.user import (
    BaseAuthUserRequestSchema,
    SignUpRequestSchema,
    SignUpResponseSchema,
)
from src.services.auth import auth_service
from src.services.email import send_email
from src.services.token_blacklist import token_blacklist_service

EMAIL_VERIFY_TITLE = "Confirm your email"
EMAIL_VERIFY_TEMPLATE = "verify_email.html"
REFRESH_TOKEN = "refresh_token"
RESET_PASSWORD_TITLE = "Reset your password"
RESET_PASSWORD_TEMPLATE = "reset_password.html"

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[
        Depends(RateLimiter(limiter=rate_limiters.auth_base_limiter))
    ],
)


@router.post(
    "/signup",
    response_model=SignUpResponseSchema,
    status_code=status.HTTP_201_CREATED,
    response_description=HTTPStatusMessages.successfully_created.value,
    dependencies=[
        Depends(
            RateLimiter(limiter=rate_limiters.auth_signup_limiter)
        )
    ],
    description=(
        "Register a new user and send an email verification link.\n\n"
        "Username requirements:\n"
        "- length must be between 3 and 30 characters\n"
        "- must start with a lowercase letter\n"
        "- may contain only lowercase letters, digits, and underscores\n"
        "- must not end with an underscore"
    ),
)
async def register(
    body: SignUpRequestSchema,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SignUpResponseSchema:
    """Register a new user and send an email verification link.

    Creates a new user account with a hashed password, generates an email
    confirmation token, and schedules a background task to send the
    verification email.
    """

    user = await repository_user.get_user_by_email(
        email=body.email, db=db
    )

    if user:
        create_exception(
            status_code=status.HTTP_409_CONFLICT,
            message=HTTPStatusMessages.account_already_exists.value,
        )

    body.password = auth_service.create_hashed_password(body.password)
    new_user = await repository_user.create_user(body=body, db=db)

    # Creating a JWT token
    email_confirm_token = auth_service.create_email_confirm_token(
        payload={"sub": new_user.email}
    )

    # Sending an email to verify user email address
    background_tasks.add_task(
        send_email,
        email=new_user.email,
        username=new_user.username,
        host=request.base_url,
        token=email_confirm_token,
        subject=EMAIL_VERIFY_TITLE,
        template_name=EMAIL_VERIFY_TEMPLATE,
    )

    return new_user


@router.post(
    "/signin",
    response_model=SignInResponse,
    response_description=HTTPStatusMessages.success.value,
    description="Authenticate a user and start a new session",
)
async def login(
    body: BaseAuthUserRequestSchema,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and start a new session.

    The endpoint resolves the user by email, validates confirmation status,
    blocked status, and password, issues a new access token and refresh
    token, stores the refresh-token hash for session revocation, stores the
    access-token JTI for active-token validation, and returns the access
    token while placing the refresh token into an ``HttpOnly`` cookie.
    """

    # Resolve the account by email before any credential checks.
    user = await repository_user.get_user_by_email(
        email=body.email, db=db
    )
    if user is None:
        create_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=HTTPStatusMessages.invalid_email_or_password.value,
        )

    if not user.confirmed:
        create_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=HTTPStatusMessages.email_not_confirmed.value,
        )

    # Blocked users must not be able to start new authenticated sessions.
    if user.blocked:
        create_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            message=HTTPStatusMessages.forbidden.value,
        )

    # Verify the submitted password against the stored bcrypt hash.
    is_match_passwords = auth_service.verify_password(
        plain_password=body.password, hashed_password=user.password
    )
    if not is_match_passwords:
        create_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=HTTPStatusMessages.invalid_email_or_password.value,
        )

    # Generate JWTs and keep the access-token JTI for active-session tracking.
    access_token, access_token_jti = auth_service.create_access_token(
        payload={"sub": user.email}
    )
    refresh_token = auth_service.create_refresh_token(
        payload={"sub": user.email}
    )
    refresh_token_hash = auth_service.get_token_hash(
        token=refresh_token
    )

    # Persist one session record for this browser/device context.
    await repository_auth.create_user_session(
        refresh_token_hash=refresh_token_hash,
        access_token_jti=access_token_jti,
        user_id=user.id,
        db=db,
    )

    response = JSONResponse(
        {"access_token": access_token, "token_type": "bearer"}
    )
    # Store the refresh token in a secure HttpOnly cookie for browser flows.
    response.set_cookie(
        key=REFRESH_TOKEN,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        # Keep cookie lifetime aligned with refresh token JWT expiration (in seconds).
        max_age=auth_service.refresh_cookie_max_age,
        # `Lax` if frontend and backend are on the same site or almost the same origin.
        # `None` if frontend and backend are on different domains/origins, but then Secure=True is required.
    )
    return response


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.success_logout.value,
    description="Log out the current session",
)
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(
        auth_service.security
    ),
):
    """Log out the current session.

    The endpoint validates the current authenticated session, reads the
    current access token from the bearer credentials, adds that access token
    to the Redis blacklist for the rest of its lifetime, removes the
    matching stored user-session record by refresh-token hash, and clears the
    refresh-token cookie. Other active sessions remain valid.
    """
    access_token = credentials.credentials

    # Revoke the current access token so it cannot be reused after logout.
    await token_blacklist_service.add_access_token_jti_to_blacklist(
        token=access_token
    )

    refresh_token = request.cookies.get(REFRESH_TOKEN)
    if refresh_token:
        # Delete the current session record identified by the refresh token.
        refresh_token_hash = auth_service.get_token_hash(
            refresh_token
        )
        await repository_auth.delete_user_session_by_refresh_token_hash(
            refresh_token_hash=refresh_token_hash,
            db=db,
        )

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_TOKEN)
    return response


@router.post(
    "/logout-from-all-devices",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.success_logout.value,
    description="Log out the user from all devices and revoke the current access token",
)
async def logout_from_all_devices(
    current_user: User = Depends(auth_service.get_current_user),
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(
        auth_service.security
    ),
):
    """Log out the user from all devices.

    The endpoint validates the current authenticated session, adds the
    current access token to the Redis blacklist for the rest of its
    lifetime, deletes all stored user-session records for the user, and
    clears the refresh-token cookie for the current device.
    """
    access_token = credentials.credentials

    # Revoke the current access token immediately for this device as well.
    await token_blacklist_service.add_access_token_jti_to_blacklist(
        token=access_token
    )

    # Delete every stored session for this user across all devices.
    await repository_auth.delete_all_user_sessions_by_user_id(
        user_id=current_user.id,
        db=db,
    )

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_TOKEN)
    return response


@router.get(
    "/confirm-email/{token}",
    response_description=HTTPStatusMessages.successful_email_verification.value,
    dependencies=[
        Depends(
            RateLimiter(
                limiter=rate_limiters.auth_confirm_email_limiter
            )
        )
    ],
    description="Confirm a user's email address",
)
async def confirm_email(
    token: str, db: AsyncSession = Depends(get_db)
):
    """Confirm a user's email address.

    Validates the email confirmation token, resolves the target user, and
    marks the email as confirmed if it has not been confirmed before.
    """

    email = auth_service.get_email_from_email_token(token)
    user = await repository_user.get_user_by_email(email=email, db=db)

    if user is None:
        create_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=HTTPStatusMessages.verification_error.value,
        )

    if user.confirmed:
        return {"message": EmailMessages.email_already_confirmed}

    await repository_user.confirm_email(email=email, db=db)
    return {"message": EmailMessages.email_confirmed}


@router.post(
    "/request-confirm-email",
    response_description=HTTPStatusMessages.success.value,
    dependencies=[
        Depends(
            RateLimiter(
                limiter=rate_limiters.auth_request_email_limiter
            )
        )
    ],
    description="Request a new email confirmation message",
)
async def request_confirm_email(
    body: RequestEmail,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Request a new email confirmation message.

    Sends a new verification email when the account exists and is not yet
    confirmed. The response stays generic to avoid disclosing whether the
    email address is registered in the system.
    """

    user = await repository_user.get_user_by_email(
        email=body.email, db=db
    )
    if user is None:
        return {
            "message": EmailMessages.check_email_forconfirmation.value
        }

    if user.confirmed:
        return {
            "message": EmailMessages.email_already_confirmed.value
        }

    verification_token = auth_service.create_email_confirm_token(
        {"sub": user.email}
    )

    background_tasks.add_task(
        send_email,
        email=user.email,
        username=user.username,
        host=request.base_url,
        token=verification_token,
        subject=EMAIL_VERIFY_TITLE,
        template_name=EMAIL_VERIFY_TEMPLATE,
    )
    return {
        "message": EmailMessages.check_email_forconfirmation.value
    }


@router.post(
    "/refresh",
    response_model=SignInResponse,
    response_description=HTTPStatusMessages.success.value,
    dependencies=[
        Depends(
            RateLimiter(
                limiter=rate_limiters.auth_refresh_token_limiter
            )
        )
    ],
    description=(
        "Issue a new access token and rotate the refresh cookie. "
        "This endpoint reads the refresh token from an HttpOnly cookie, so "
        "browser clients must send the request with credentials: 'include'."
    ),
)
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Issue a new access token and rotate the refresh token.

    The endpoint reads the refresh token from the ``refresh_token`` cookie,
    validates the token and its owner, rejects blocked users, verifies that
    the current refresh-token session still exists in the database, issues a
    new access token and a rotated refresh token, updates the stored
    refresh-token hash for that session, stores the new access-token JTI for
    active-token validation, and returns the new access token while updating
    the refresh-token cookie. Browser clients must send this request with
    ``credentials: "include"`` so the cookie is included.
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=HTTPStatusMessages.could_not_validate_token.value,
        headers={"WWW-Authenticate": "Bearer"},
    )

    refresh_token = request.cookies.get(REFRESH_TOKEN)
    if refresh_token is None:
        raise credentials_exception

    email = await auth_service.get_email_from_refresh_token(
        refresh_token=refresh_token, db=db
    )
    user = await repository_user.get_user_by_email(email=email, db=db)
    if user is None:
        raise credentials_exception

    # Blocked users must not be able to refresh authentication tokens.
    if user.blocked:
        create_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            message=HTTPStatusMessages.forbidden.value,
        )

    old_refresh_token_hash = auth_service.get_token_hash(
        token=refresh_token
    )

    # Ensure that this exact user session still exists before rotation.
    session = (
        await repository_auth.get_user_session_by_refresh_token_hash(
            refresh_token_hash=old_refresh_token_hash,
            db=db,
        )
    )
    if session is None:
        raise credentials_exception

    # Issue a fresh access token and rotate the refresh token for this session.
    access_token, access_token_jti = auth_service.create_access_token(
        payload={"sub": email}
    )
    new_refresh_token = auth_service.create_refresh_token(
        payload={"sub": email}
    )
    new_refresh_token_hash = auth_service.get_token_hash(
        token=new_refresh_token
    )

    # Rotate both token identifiers inside the same persisted session record.
    updated_session = (
        await repository_auth.update_user_session_tokens(
            old_refresh_token_hash=old_refresh_token_hash,
            new_refresh_token_hash=new_refresh_token_hash,
            new_access_token_jti=access_token_jti,
            db=db,
        )
    )

    if updated_session is None:
        raise credentials_exception

    response = JSONResponse(
        {"access_token": access_token, "token_type": "bearer"}
    )
    # Replace the browser refresh-token cookie with the rotated token value.
    response.set_cookie(
        key=REFRESH_TOKEN,
        value=new_refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        # Keep cookie lifetime aligned with refresh token JWT expiration (in seconds).
        max_age=auth_service.refresh_cookie_max_age,
    )
    return response


@router.post(
    "/password-reset/request",
    response_model=MessageResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    dependencies=[
        Depends(
            RateLimiter(
                limiter=rate_limiters.auth_reset_password_limiter
            )
        )
    ],
    description=(
        "Request a password reset email.\n\n"
        """When the account exists, the endpoint creates or replaces the
        current password-reset token for that user and sends an email with
        the reset link. The response stays generic even when the email does
        not exist."""
    ),
)
async def password_reset_request(
    body: RequestEmail,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Request a password reset email for an existing account.

    The endpoint resolves the user by email, and when the account exists it
    creates a short-lived password-reset token, stores its hash in the
    database, and schedules a reset email to be sent in the background. The
    response remains generic to avoid disclosing whether the email exists.
    """

    # Resolve the account by email, but do not expose whether it exists.
    user = await repository_user.get_user_by_email(
        email=body.email, db=db
    )

    if user:
        # Create the raw reset token for the email link and persist only its hash.
        token = auth_service.create_reset_password_token(
            {"sub": user.email}
        )
        token_hash = auth_service.get_token_hash(token=token)

        # Keep one active password-reset token record per user.
        await repository_auth.create_password_reset_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(
                minutes=auth_service.password_reset_token_minutes
            ),
            db=db,
        )

        # Send the reset email asynchronously so the API response is immediate.
        background_tasks.add_task(
            send_email,
            email=user.email,
            username=user.username,
            host=request.base_url,
            token=token,
            subject=RESET_PASSWORD_TITLE,
            template_name=RESET_PASSWORD_TEMPLATE,
        )

    return {
        "message": EmailMessages.reset_password_email_exists.value
    }


@router.get(
    "/password-reset/verify/{token}",
    # status_code=status.HTTP_302_FOUND,
    # responses={302: {"description": "Redirect to frontend reset page"}},
    # description=(
    #     "Validate the password reset token and redirect the user to the "
    #     "frontend password reset page when the token is valid."
    # ),
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Validate a password reset token.\n\n"
        """This temporary REST-only version checks whether the token is valid,
        exists in the database, has not been used yet, and has not expired.
        When validation succeeds, the endpoint returns `204 No Content`."""
    ),
)
async def password_reset_verify_token(
    token: str, db: AsyncSession = Depends(get_db)
) -> Response:
    """Validate a password reset token and return success with no body.

    This endpoint is currently used without a frontend redirect. It verifies
    the JWT itself together with the stored password-reset token state in the
    database and returns ``204 No Content`` when the token is valid.
    """

    await auth_service.validate_password_reset_token(
        token=token, db=db
    )

    # frontend_url = (
    #     f"{settings.FRONTEND_URL}/reset-password?token={token}"
    # )
    # return RedirectResponse(url=frontend_url, status_code=status.HTTP_302_FOUND)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Confirm a password reset and save the new password.\n\n"
        """The endpoint validates the provided password reset token again,
        updates the user's stored password hash, marks the reset token as
        used, and returns `204 No Content` when the password change succeeds."""
    ),
)
async def password_reset_confirm(
    body: ResetPasswordRequestSchema,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Confirm a password reset and persist the new password.

    The endpoint revalidates the password reset token against JWT and
    database state, updates the user's stored password hash, marks the
    password reset token as used, and returns ``204 No Content`` on success.
    """

    email = await auth_service.validate_password_reset_token(
        token=body.token, db=db
    )

    updated_user = await repository_user.update_user_password(
        email=email,
        hashed_password=auth_service.create_hashed_password(
            plain_password=body.password
        ),
        db=db,
    )
    if updated_user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=HTTPStatusMessages.invalid_or_expired_password_reset_token.value,
        )

    token_hash = auth_service.get_token_hash(body.token)
    await repository_auth.mark_password_reset_token_as_used(
        token_hash, db=db
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
