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
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import EmailMessages, HTTPStatusMessages
from src.database.db import get_db
from src.entity.user import User
from src.repository import auth as repository_auth
from src.repository import user as repository_user
from src.schemas.auth import RequestEmail, SignInResponse
from src.schemas.user import BaseUserSchema, UserResponse, UserSchema
from src.services.auth import auth_service
from src.services.email import send_email

EMAIL_VERIFY_TITLE = "Confirm your email"
EMAIL_VERIFY_TEMPLATE = "verify_email.html"
REFRESH_TOKEN = "refresh_token"

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    response_description=HTTPStatusMessages.successfully_created.value,
    description="Register a new user and send an email verification link",
)
async def register(
    body: UserSchema,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user and send an email verification link.

    Creates a new user account with a hashed password, generates an email
    confirmation token, and schedules a background task to send the
    verification email.
    """

    user = await repository_user.get_user_by_email(email=body.email, db=db)

    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=HTTPStatusMessages.account_already_exists.value,
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


# TODO Додати редіс для аксес токнів, блок-ліста
@router.post(
    "/signin",
    response_model=SignInResponse,
    response_description=HTTPStatusMessages.success,
    description="Authenticate a user and start a new session",
)
async def login(body: BaseUserSchema, db: AsyncSession = Depends(get_db)):
    """Authenticate a user and start a new session.

    Validates user credentials, returns an access token in the response body,
    and stores the refresh token in an ``HttpOnly`` cookie. A hash of the
    refresh token is persisted in the database so each login creates its own
    revocable session.
    """

    user = await repository_user.get_user_by_email(email=body.email, db=db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=HTTPStatusMessages.invalid_email_or_password.value,
        )

    if not user.confirmed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=HTTPStatusMessages.email_not_confirmed.value,
        )

    is_match_passwords = auth_service.verify_password(
        plain_password=body.password, hashed_password=user.password
    )
    if not is_match_passwords:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=HTTPStatusMessages.invalid_email_or_password.value,
        )

    # Generate JWT
    access_token = auth_service.create_access_token(payload={"sub": user.email})
    refresh_token = auth_service.create_refresh_token(payload={"sub": user.email})
    hash_refresh_token = auth_service.get_token_hash(token=refresh_token)

    await repository_auth.add_refresh_token(
        hash_token=hash_refresh_token, user_id=user.id, db=db
    )

    response = JSONResponse({"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key=REFRESH_TOKEN,
        value=refresh_token,
        httponly=True,
        secure=True,
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
    current_user: User = Depends(auth_service.get_current_user),
):
    """Log out the current session.

    Reads the refresh token from the ``refresh_token`` cookie, removes the
    matching stored token hash from the database, and clears the cookie in the
    response. Other active sessions on other devices remain valid.
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN)
    if refresh_token:
        hash_refresh_token = auth_service.get_token_hash(token=refresh_token)
        await repository_auth.delete_refresh_token_by_token(
            hash_token=hash_refresh_token, db=db
        )

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_TOKEN)
    return response


@router.post(
    "/logout-from-all-devices",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.success_logout.value,
    description="Log out the user from all devices",
)
async def logout_from_all_devices(
    current_user: User = Depends(auth_service.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log out the user from all devices.

    Resolves the currently authenticated user from the access token, deletes
    all refresh tokens that belong to that user, and clears the refresh token
    cookie for the current device.
    """
    await repository_auth.delete_all_refresh_tokens_by_user_id(
        user_id=current_user.id, db=db
    )

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_TOKEN)
    return response


@router.get(
    "/confirm-email/{token}",
    response_description=HTTPStatusMessages.successful_email_verification.value,
    description="Confirm a user's email address",
)
async def confirm_email(token: str, db: AsyncSession = Depends(get_db)):
    """Confirm a user's email address.

    Validates the email confirmation token, resolves the target user, and
    marks the email as confirmed if it has not been confirmed before.
    """

    email = auth_service.get_email_from_email_token(token)
    user = await repository_user.get_user_by_email(email=email, db=db)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=HTTPStatusMessages.verification_error.value,
        )

    if user.confirmed:
        return {"message": EmailMessages.email_already_confirmed}

    await repository_user.confirm_email(email=email, db=db)
    return {"message": EmailMessages.email_confirmed}


@router.post(
    "/request-confirm-email",
    response_description=HTTPStatusMessages.success.value,
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

    user = await repository_user.get_user_by_email(email=body.email, db=db)
    if user is None:
        return {"message": EmailMessages.check_email_forconfirmation.value}

    if user.confirmed:
        return {"message": EmailMessages.email_already_confirmed.value}

    verification_token = auth_service.create_email_confirm_token({"sub": user.email})

    background_tasks.add_task(
        send_email,
        email=user.email,
        username=user.username,
        host=request.base_url,
        token=verification_token,
        subject=EMAIL_VERIFY_TITLE,
        template_name=EMAIL_VERIFY_TEMPLATE,
    )
    return {"message": EmailMessages.check_email_forconfirmation.value}


@router.post(
    "/refresh",
    response_model=SignInResponse,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Issue a new access token and rotate the refresh cookie. "
        "This endpoint reads the refresh token from an HttpOnly cookie, so "
        "browser clients must send the request with credentials: 'include'."
    ),
)
async def refresh_token(
    request: Request, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    """Issue a new access token and rotate the refresh token.

    Reads the refresh token from the ``refresh_token`` cookie, validates it,
    ensures the current session is still active in the database, and rotates
    the refresh token by replacing its stored hash and cookie value. Browser
    clients must send this request with ``credentials: "include"`` so the
    cookie is included.
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

    old_refresh_token_hash = auth_service.get_token_hash(token=refresh_token)
    deleted = await repository_auth.delete_refresh_token_by_token(
        hash_token=old_refresh_token_hash, db=db
    )
    if not deleted:
        raise credentials_exception

    access_token = auth_service.create_access_token(payload={"sub": email})
    new_refresh_token = auth_service.create_refresh_token(payload={"sub": email})
    new_refresh_token_hash = auth_service.get_token_hash(token=new_refresh_token)

    await repository_auth.add_refresh_token(
        hash_token=new_refresh_token_hash, user_id=user.id, db=db
    )

    response = JSONResponse({"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key=REFRESH_TOKEN,
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        # Keep cookie lifetime aligned with refresh token JWT expiration (in seconds).
        max_age=auth_service.refresh_cookie_max_age,
    )
    return response
