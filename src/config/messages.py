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
    operation_forbidden = "Operation forbidden"
    bad_request = "Bad request"

    failed_apload_photo_to_Cloudinary = (
        "Failed to upload photo to Cloudinary."
    )
    failed_delete_photo_from_Cloudinary = (
        "Failed to delete photo from Cloudinary."
    )
    failed_apload_qr_to_Cloudinary = (
        "Failed to upload QR code to Cloudinary."
    )

    tag_already_exists = "Tag already exists"


class EmailMessages(Enum):
    email_confirmed = "Email confirmed"
    email_already_confirmed = "Your email is already confirmed."
    check_email_forconfirmation = "Check your email for confirmation."


class UserValidationMessages(Enum):
    password_requires_lowercase = (
        "Password must contain at least one lowercase letter."
    )
    password_requires_uppercase = (
        "Password must contain at least one uppercase letter."
    )
    password_requires_digit = (
        "Password must contain at least one digit."
    )
    password_requires_special_character = (
        "Password must contain at least one special character: "
    )
    username_has_invalid_format = "Username must start with a lowercase letter and contain only lowercase letters, digits, and underscores, and it must not end with an underscore."
    display_name_must_not_be_empty = "Display name must not be empty."
    display_name_contains_invalid_characters = "Display name may contain only letters, spaces, hyphens, and apostrophes."


OWNER_OR_ADMIN_ACCESS = "Accessible by the photo owner or an admin."
AUTHENTICATED_USERS_ACCESS = "Available for authenticated users."
STAFF_ACCESS = "Available for administrators and moderators."


class PhotoTransformationMessage(Enum):
    resize_requires_both_width_and_height = (
        "Resize requires both width and height."
    )
    crop_requires_both_width_and_height = (
        "Crop requires both width and height."
    )
    rotate_equires_angle = "Rotate requires angle."
    blur_requires_blur_radius = "Blur requires blur_radius."
    unsupported_transformation_type = (
        "Unsupported transformation type."
    )
