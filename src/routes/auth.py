from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import EmailMessages, HTTPStatusMessages
from src.database.db import get_db
from src.repository import auth as repository_auth
from src.repository import user as repository_user
from src.schemas.user import BaseUserSchema, TokenSchema, UserResponse, UserShcema
from src.services.auth import auth_service
from src.services.email import send_email

EMAIL_VERIFY_TITLE = "Confirm your email"
EMAIL_VERIFY_TEMPLATE = "verify_email.html"

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    response_description=HTTPStatusMessages.successfully_created.value,
)
async def register(
    body: UserShcema,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user and send an email for verification."""

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


@router.post(
    "/signin",
    response_model=TokenSchema,
    response_description=HTTPStatusMessages.success,
)
async def login(body: BaseUserSchema, db: AsyncSession = Depends(get_db)):
    """Authenticate a user and return access and refresh tokens."""

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

    await repository_auth.add_refresh_token(token=refresh_token, user_id=user.id, db=db)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.get(
    "/confirm-email/{token}",
    response_description=HTTPStatusMessages.successful_email_verification.value,
)
async def confirm_email(token: str, db: AsyncSession = Depends(get_db)):
    """Confirm a user email address."""

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
