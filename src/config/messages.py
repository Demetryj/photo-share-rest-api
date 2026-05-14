from enum import Enum


class HTTPStatusMessages(Enum):
    success = "Success"
    successfully_created = "Successfully created"
    successful_email_verification = "Successful email verification"
    account_already_exists = "Account already exists"
    success_logout = "Successfully logged out"
    successfully_deleted = "Successfully deleted"

    invalid_token_for_email_verification = (
        "Invalid token for email verification"
    )
    verification_error = "Verification error"
    invalid_email_or_password = "Invalid email or password"
    email_not_confirmed = "Email not confirmed"
    could_not_validate_credentials = "Could not validate credentials"
    could_not_validate_token = "Could not validate token"
    not_found = "Not found"
    forbidden = "Forbidden"
    access_denied = "Access denied"

    failed_apload_photo_to_Cloudinary = (
        "Failed to upload photo to Cloudinary"
    )
    failed_delete_photo_from_Cloudinary = (
        "Failed to delete photo from Cloudinary."
    )

    tag_already_exists = "Tag already exists"


class EmailMessages(Enum):
    email_confirmed = "Email confirmed"
    email_already_confirmed = "Your email is already confirmed."
    check_email_forconfirmation = "Check your email for confirmation."
