import enum
from io import BytesIO

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from src.config.messages import HTTPStatusMessages
from src.config.settings import settings
from src.entity.photo import Photo
from src.entity.user import Role, User


class ImageFormat(enum.Enum):
    """Supported image file formats that can be accepted from user uploads."""

    jpg = "jpg"
    jpeg = "jpeg"
    png = "png"
    webp = "webp"


MAX_IMAGE_SIZE = 1 * 1024 * 1024  # 1 MB limit
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

MAX_NUMBER_TAGS = 5

cloudinary.config(
    cloud_name=settings.CLOUDINARY_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


async def validate_image_file(file: UploadFile) -> None:
    """Validate an uploaded image before further processing.

    This function performs a basic set of checks for user-uploaded image files:
    it verifies the MIME type declared by the client, enforces the maximum file
    size limit, confirms that the uploaded binary content is a real image, and
    ensures that the detected image format is one of the allowed formats.

    The function does not return any value. If validation fails, it raises an
    ``HTTPException`` with status code ``400 Bad Request`` and a descriptive
    error message. If validation succeeds, the file pointer is reset so the same
    ``UploadFile`` object can be reused later, for example for upload to
    Cloudinary or further image processing.

    Args:
        file: Uploaded image file received from the client.

    Raises:
        HTTPException: If the MIME type is not allowed, the file exceeds the
            maximum size, the content is not a valid image, or the detected
            image format is not supported.
    """

    # Check the MIME type sent by the client before reading the file content.
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WEBP images are allowed.",
        )

    # Read the uploaded file into memory once.
    content = await file.read()

    # Reject files larger than the configured size limit.
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image size must not exceed 1 MB.",
        )

    try:
        # Try to open the file as an image to ensure the binary content is valid.
        image = Image.open(BytesIO(content))

        # Verify that the file is not corrupted and is a real image.
        image.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid image.",
        )

    # Re-open the image after verify(), because Pillow leaves the object unusable.
    image = Image.open(BytesIO(content))

    # Check the actual detected image format, not just the client-provided MIME type.
    if image.format not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WEBP images are allowed.",
        )

    # Reset the file pointer so the file can be reused later, for example for upload to Cloudinary.
    await file.seek(0)


def normalize_image_tags(tags: list[str] | None) -> list[str]:
    """Normalize and validate photo tags provided by the client.

    The function removes surrounding whitespace, converts tags to lowercase,
    ignores empty values, enforces the maximum allowed number of tags per
    photo, and ensures that each resulting tag is unique.

    """

    normalized_tags = [
        tag.strip().lower() for tag in tags or [] if tag.strip()
    ]

    if len(normalized_tags) > MAX_NUMBER_TAGS:
        raise ValueError(
            f"You can add up to {MAX_NUMBER_TAGS} tags per photo."
        )

    if len(normalized_tags) != len(set(normalized_tags)):
        raise ValueError("Tags must be unique.")

    return normalized_tags


async def cloudinary_upload(file: UploadFile, public_id: str) -> str:
    """Upload an image file to Cloudinary and return its generated URL.

    The function sends the uploaded file object to Cloudinary using the provided
    public identifier. If the upload succeeds, it builds and returns the final
    CDN URL for the stored image based on the uploaded asset version.
    """

    # Upload the new photo to Cloudinary under a stable user-specific public id.
    try:
        res = cloudinary.uploader.upload(
            file.file, public_id=public_id
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=HTTPStatusMessages.failed_apload_photo_to_Cloudinary.value,
        ) from err

    res_url = cloudinary.CloudinaryImage(public_id).build_url(
        version=res.get("version")
    )

    return res_url


async def cloudinary_delete(public_id: str) -> None:
    """Delete an uploaded image from Cloudinary by its public identifier."""

    try:
        result = cloudinary.uploader.destroy(public_id)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=HTTPStatusMessages.failed_delete_photo_from_Cloudinary.value,
        ) from err

    if result.get("result") not in {"ok", "not found"}:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=HTTPStatusMessages.failed_delete_photo_from_Cloudinary.value,
        )


def check_photo_owner_or_admin_access(
    photo: Photo, current_user: User
) -> None:
    """Allow the operation only for the owner of the photo or an admin.

    The function compares the authenticated user's id with the photo owner's
    id and also allows administrators to proceed. It raises ``403 Forbidden``
    when a user is neither the owner nor an admin.
    """

    if (
        photo.owner_id != current_user.id
        and current_user.role != Role.admin
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=HTTPStatusMessages.access_denied.value,
        )
