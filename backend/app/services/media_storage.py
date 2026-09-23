"""Safe media storage for uploaded product files.

Security rules:
- never trust the client/Telegram supplied filename
- generate unique filenames ourselves
- validate size before and after download
- validate MIME type against an allow-list
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models import MediaType

logger = get_logger(__name__)

# Maps an allow-listed MIME type to the extension we store it as.
_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_VIDEO_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}

MAX_FILENAME_LENGTH = 200


class MediaError(Exception):
    """Base class for media problems that are safe to show a user."""


class MediaTooLargeError(MediaError):
    pass


class MediaTypeNotAllowedError(MediaError):
    pass


class MediaDownloadError(MediaError):
    pass


@dataclass(frozen=True)
class StoredMedia:
    file_path: str
    mime_type: str
    file_size: int
    media_type: MediaType
    original_filename: str | None = None


def _normalize_mime(mime: str | None) -> str:
    return (mime or "").split(";")[0].strip().lower()


def resolve_media_type(mime: str) -> MediaType | None:
    """Return which MediaType this MIME belongs to, or None if not allowed."""
    if mime in settings.allowed_image_types and mime in _IMAGE_EXTENSIONS:
        return MediaType.image
    if mime in settings.allowed_video_types and mime in _VIDEO_EXTENSIONS:
        return MediaType.video
    return None


def extension_for(mime: str) -> str:
    return _IMAGE_EXTENSIONS.get(mime) or _VIDEO_EXTENSIONS.get(mime) or ".bin"


def sanitize_filename(name: str | None) -> str | None:
    """Keep a human-readable name for display only; never used as a path."""
    if not name:
        return None
    cleaned = Path(name).name  # strip any directory components
    cleaned = cleaned.replace("\x00", "").strip()
    if not cleaned:
        return None
    return cleaned[:MAX_FILENAME_LENGTH]


def uploads_root() -> Path:
    root = Path(settings.uploads_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_relative_path(product_id, media_type: MediaType, mime: str) -> str:
    ext = extension_for(mime)
    unique = uuid.uuid4().hex
    return f"products/{product_id}/{media_type.value}/{unique}{ext}"


def validate_declared_size(size: int | None) -> None:
    """Check the size Telegram reports before downloading."""
    if size is not None and size > settings.media_max_file_size_bytes:
        limit_mb = settings.media_max_file_size_mb
        raise MediaTooLargeError(
            f"Ukuran file melebihi batas {limit_mb} MB."
        )


def validate_mime(mime: str | None) -> tuple[str, MediaType]:
    normalized = _normalize_mime(mime)
    if not normalized:
        raise MediaTypeNotAllowedError("Tipe file tidak dikenali.")
    if normalized not in settings.allowed_image_types and normalized not in settings.allowed_video_types:
        raise MediaTypeNotAllowedError(
            f"Tipe file '{normalized}' tidak diizinkan."
        )
    resolved = resolve_media_type(normalized)
    if resolved is None:
        raise MediaTypeNotAllowedError(
            f"Tipe file '{normalized}' tidak didukung."
        )
    return normalized, resolved


async def download_to_storage(
    *,
    url: str,
    product_id,
    mime: str | None,
    declared_size: int | None = None,
    original_filename: str | None = None,
) -> StoredMedia:
    """Download media to local storage with validation. Token is never logged."""
    validate_declared_size(declared_size)
    mime_type, media_type = validate_mime(mime)

    relative_path = build_relative_path(product_id, media_type, mime_type)
    destination = uploads_root() / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    limit = settings.media_max_file_size_bytes
    written = 0

    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
            async with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise MediaDownloadError(
                        f"Gagal mengunduh file (HTTP {response.status_code})."
                    )
                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        written += len(chunk)
                        if written > limit:
                            handle.close()
                            destination.unlink(missing_ok=True)
                            raise MediaTooLargeError(
                                f"Ukuran file melebihi batas "
                                f"{settings.media_max_file_size_mb} MB."
                            )
                        handle.write(chunk)
    except MediaError:
        raise
    except httpx.HTTPError as exc:
        destination.unlink(missing_ok=True)
        raise MediaDownloadError(
            f"Gagal mengunduh file: {type(exc).__name__}"
        ) from exc
    except OSError as exc:
        destination.unlink(missing_ok=True)
        logger.exception("Failed writing media to disk")
        raise MediaDownloadError("Gagal menyimpan file ke storage.") from exc

    if written == 0:
        destination.unlink(missing_ok=True)
        raise MediaDownloadError("File yang diunduh kosong.")

    return StoredMedia(
        file_path=relative_path,
        mime_type=mime_type,
        file_size=written,
        media_type=media_type,
        original_filename=sanitize_filename(original_filename),
    )


def save_bytes(
    *,
    data: bytes,
    product_id,
    mime: str | None,
    original_filename: str | None = None,
) -> StoredMedia:
    """Store already-in-memory bytes (used by tests and future HTTP uploads)."""
    validate_declared_size(len(data))
    mime_type, media_type = validate_mime(mime)

    relative_path = build_relative_path(product_id, media_type, mime_type)
    destination = uploads_root() / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    if len(data) > settings.media_max_file_size_bytes:
        raise MediaTooLargeError(
            f"Ukuran file melebihi batas {settings.media_max_file_size_mb} MB."
        )

    try:
        destination.write_bytes(data)
    except OSError as exc:
        logger.exception("Failed writing media to disk")
        raise MediaDownloadError("Gagal menyimpan file ke storage.") from exc

    return StoredMedia(
        file_path=relative_path,
        mime_type=mime_type,
        file_size=len(data),
        media_type=media_type,
        original_filename=sanitize_filename(original_filename),
    )


def delete_stored(path: str) -> None:
    """Best-effort removal; never raises."""
    try:
        (uploads_root() / path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not delete media file %s", path)
