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


OWNER_OR_ADMIN_ACCESS = "Accessible by the photo owner or an admin."


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
