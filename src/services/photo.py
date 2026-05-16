import enum
from datetime import datetime, timezone
from io import BytesIO
from typing import NoReturn

import cloudinary
import cloudinary.uploader
import httpx
import qrcode
from fastapi import HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image, ImageFilter, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import (
    HTTPStatusMessages,
    PhotoTransformationMessage,
)
from src.config.settings import settings
from src.entity.photo import BlurMode, Photo, Tag, TransformationType
from src.entity.user import Role, User
from src.repository import photo as repository_photo
from src.schemas.photo import (
    PhotoResponseSchema,
    PhotoTransformationRequestSchema,
    TagResponseShema,
)


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
HTTP_CLIENT_TIMEOUT = 30.0
PREVIEW_IMAGE_FORMAT = "JPEG"
PREVIEW_MEDIA_TYPE = "image/jpeg"
QR_IMAGE_FORMAT = "PNG"
CLOUDINARY_IMAGE_RESOURCE_TYPE = "image"
CLOUDINARY_CROP_FILL = "fill"
CLOUDINARY_CROP_CROP = "crop"
CLOUDINARY_EFFECT_GRAYSCALE = "grayscale"

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


async def prepare_photo_tags(
    tags: list[str] | None,
    db: AsyncSession,
) -> tuple[list[Tag], list[TagResponseShema]]:
    """Normalize, resolve, and serialize photo tags for write operations.

    The function validates and normalizes tag names, reuses existing tag
    entities or creates missing ones, and builds response schemas before the
    caller commits the parent photo change.
    """

    try:
        # Normalize user-provided tag names early, so invalid tag input fails
        # before we upload anything to Cloudinary or write to the database.
        normalized_tags = normalize_image_tags(tags)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    # Reuse existing tags when possible; create missing ones in the same
    # transaction so the final photo save can commit everything together.
    tag_list: list[Tag] = [
        await repository_photo.get_or_create_tag(tag=tag, db=db)
        for tag in normalized_tags
    ]

    # Build response tag schemas before the final photo save commits the
    # session, because ORM tag objects may be expired after commit and trigger
    # async lazy loading when Pydantic tries to read their attributes.
    tags_for_resp = [
        TagResponseShema.model_validate(tag) for tag in tag_list
    ]

    return tag_list, tags_for_resp


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


async def get_photo_for_owner_or_admin(
    photo_id: int,
    current_user: User,
    db: AsyncSession,
) -> Photo:
    """Return a photo if it exists and is accessible to the owner or an admin.

    The function fetches the photo by its identifier, raises a 404 error if
    it does not exist, verifies that the current user is either the photo
    owner or an administrator, and returns the photo entity for further use.
    """

    photo = await repository_photo.get_photo_by_id(
        photo_id=photo_id, db=db
    )

    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTPStatusMessages.not_found.value,
        )

    # Allow access only for the owner of the target photo or an admin.
    check_photo_owner_or_admin_access(
        photo=photo, current_user=current_user
    )

    return photo


def build_photo_response(
    photo: Photo, tags: list[Tag] | None = None
) -> PhotoResponseSchema:
    """Build a photo response schema from a photo entity and its tags."""

    # Use explicitly provided tags when the caller already has a safe loaded
    # list; otherwise fall back to the ORM relationship on the photo entity.
    source_tags = tags if tags is not None else photo.tags

    return PhotoResponseSchema(
        id=photo.id,
        owner_id=photo.owner_id,
        description=photo.description,
        image_url=photo.image_url,
        tags=[
            TagResponseShema.model_validate(tag)
            for tag in source_tags
        ],
        created_at=photo.created_at,
    )


def create_exception(
    message: PhotoTransformationMessage | str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> NoReturn:
    """Raise an HTTP exception with the provided status code and message."""

    raise HTTPException(
        status_code=status_code,
        detail=message,
    )


def build_transformation_params(
    body: PhotoTransformationRequestSchema,
) -> dict:
    """Validate and normalize transformation parameters for preview and save.

    The function validates the parameter set according to the selected
    transformation type and returns a normalized dictionary that can be used
    both for local preview generation and Cloudinary URL building.
    """

    transformation_type = body.transformation_type
    params: dict = {}

    if transformation_type == TransformationType.resize:
        if body.width is None or body.height is None:
            create_exception(
                PhotoTransformationMessage.resize_requires_both_width_and_height.value
            )
        params["width"] = body.width
        params["height"] = body.height

    elif transformation_type == TransformationType.crop:
        if body.width is None or body.height is None:
            create_exception(
                PhotoTransformationMessage.crop_requires_both_width_and_height.value
            )
        params["width"] = body.width
        params["height"] = body.height
        params["x"] = body.x or 0
        params["y"] = body.y or 0

    elif transformation_type == TransformationType.rotate:
        if body.angle is None:
            create_exception(
                PhotoTransformationMessage.rotate_equires_angle.value
            )
        params["angle"] = body.angle
        params["expand"] = body.expand
        if body.background:
            params["background"] = body.background

    elif transformation_type == TransformationType.blur:
        if body.blur_radius is None:
            create_exception(
                PhotoTransformationMessage.blur_requires_blur_radius.value
            )
        params["blur_mode"] = body.blur_mode
        params["blur_radius"] = body.blur_radius

    elif transformation_type == TransformationType.grayscale:
        params = {}

    else:
        create_exception(
            PhotoTransformationMessage.unsupported_transformation_type.value
        )

    return params


async def download_original_photo(photo: Photo) -> bytes:
    """Download the original photo bytes from its stored URL.

    The function sends an HTTP request to the stored original image URL,
    validates the response status, and returns the downloaded binary content
    so it can be used for local preview transformations.
    """

    async with httpx.AsyncClient(
        timeout=HTTP_CLIENT_TIMEOUT
    ) as client:
        response = await client.get(photo.image_url)
        response.raise_for_status()
        return response.content


def apply_preview_transformation(
    image: Image.Image,
    transformation_type: TransformationType,
    params: dict,
) -> Image.Image:
    """Apply a local preview transformation to a Pillow image.

    The function mirrors the application's supported transformation set for
    preview purposes without creating any derived asset in Cloudinary.
    """

    if transformation_type == TransformationType.resize:
        return image.resize((params["width"], params["height"]))

    if transformation_type == TransformationType.crop:
        x = params["x"]
        y = params["y"]
        width = params["width"]
        height = params["height"]
        return image.crop((x, y, x + width, y + height))

    if transformation_type == TransformationType.rotate:
        fillcolor = params.get("background")
        return image.rotate(
            -params["angle"],
            expand=params.get("expand", False),
            fillcolor=fillcolor,
        )

    if transformation_type == TransformationType.blur:
        radius = params["blur_radius"]
        if params["blur_mode"] == BlurMode.box:
            return image.filter(ImageFilter.BoxBlur(radius))
        return image.filter(ImageFilter.GaussianBlur(radius))

    if transformation_type == TransformationType.grayscale:
        return image.convert("L").convert("RGB")

    create_exception(
        PhotoTransformationMessage.unsupported_transformation_type.value
    )


async def build_preview_response(
    photo: Photo,
    transformation_type: TransformationType,
    params: dict,
) -> StreamingResponse:
    """Build a preview image response for a transformed photo.

    The function downloads the original image, applies the requested
    transformation locally with Pillow, and returns the resulting image as a
    streamed JPEG response.
    """

    original_bytes = await download_original_photo(photo)
    image = Image.open(BytesIO(original_bytes)).convert("RGB")

    preview_image = apply_preview_transformation(
        image=image,
        transformation_type=transformation_type,
        params=params,
    )

    output = BytesIO()
    preview_image.save(output, format=PREVIEW_IMAGE_FORMAT)
    output.seek(0)

    return StreamingResponse(output, media_type=PREVIEW_MEDIA_TYPE)


def build_cloudinary_transformation_options(
    transformation_type: TransformationType,
    params: dict,
) -> list[dict]:
    """Build Cloudinary transformation options from normalized params.

    The function converts validated transformation parameters into the
    Cloudinary transformation format used to generate final saved image
    URLs for the supported transformation types.
    """

    if transformation_type == TransformationType.resize:
        return [
            {
                "width": params["width"],
                "height": params["height"],
                "crop": CLOUDINARY_CROP_FILL,
            }
        ]

    if transformation_type == TransformationType.crop:
        return [
            {
                "width": params["width"],
                "height": params["height"],
                "x": params["x"],
                "y": params["y"],
                "crop": CLOUDINARY_CROP_CROP,
            }
        ]

    if transformation_type == TransformationType.rotate:
        options = [{"angle": params["angle"]}]
        if params.get("background"):
            options[0]["background"] = params["background"]
        return options

    if transformation_type == TransformationType.blur:
        # Cloudinary blur strength is represented as an effect string.
        return [{"effect": f"blur:{params['blur_radius'] * 100}"}]

    if transformation_type == TransformationType.grayscale:
        return [{"effect": CLOUDINARY_EFFECT_GRAYSCALE}]

    create_exception(
        PhotoTransformationMessage.unsupported_transformation_type.value
    )


def build_transformed_photo_url(
    photo: Photo,
    transformation_type: TransformationType,
    params: dict,
) -> str:
    """Build and return a Cloudinary URL for a transformed version of the photo."""

    transformation = build_cloudinary_transformation_options(
        transformation_type=transformation_type,
        params=params,
    )

    return cloudinary.CloudinaryImage(photo.public_id).build_url(
        transformation=transformation
    )


async def generate_qr_code_url(
    transformed_url: str,
    photo_id: int,
    user_id: int,
) -> str:
    """Generate a QR code image for a transformed URL and upload it to Cloudinary.

    The function creates a QR code that points to the transformed image URL,
    serializes it into an in-memory PNG image, uploads that image to
    Cloudinary under a user-specific public identifier, and returns the final
    QR code URL.
    """

    # Generate the QR image in memory so it can be uploaded to Cloudinary
    # without writing any temporary file to local disk.
    qr_image = qrcode.make(transformed_url)
    buffer = BytesIO()
    qr_image.save(buffer, format=QR_IMAGE_FORMAT)
    buffer.seek(0)

    qr_public_id = f"photo_share/qr_codes/{user_id}/{photo_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    try:
        result = cloudinary.uploader.upload(
            buffer,
            public_id=qr_public_id,
            resource_type=CLOUDINARY_IMAGE_RESOURCE_TYPE,
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=HTTPStatusMessages.failed_apload_qr_to_Cloudinary.value,
        ) from err

    return result["secure_url"]
