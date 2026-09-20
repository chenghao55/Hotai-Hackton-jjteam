"""Minimal local filesystem storage for vehicle borrow and return photos."""

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from uuid import uuid4


class PhotoType(str, Enum):
    BORROW = "borrow"
    RETURN = "return"


@dataclass(frozen=True)
class Photo:
    photo_id: str
    photo_type: PhotoType
    file_path: Path


class PhotoNotFoundError(LookupError):
    """Raised when no locally stored photo matches a supplied photo ID."""


# Kept as a module value so tests can use isolated temporary storage.
PHOTOS_DIR = Path(__file__).resolve().parent.parent / "photos"


def _metadata_path(photo_id: str) -> Path:
    return PHOTOS_DIR / f"{photo_id}.json"


def _load_photo(photo_id: str) -> Photo:
    """
    把photo加載成Photo class\n
    """
    
    metadata_path = _metadata_path(photo_id)
    if not isinstance(photo_id, str) or not photo_id or not metadata_path.is_file():
        raise PhotoNotFoundError(f"Photo not found: {photo_id!r}")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        stored_photo_id = metadata["photo_id"]
        photo_type = PhotoType(metadata["photo_type"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PhotoNotFoundError(f"Photo metadata is invalid: {photo_id!r}") from exc

    if stored_photo_id != photo_id:
        raise PhotoNotFoundError(f"Photo metadata does not match: {photo_id!r}")

    photo = Photo(
        photo_id=stored_photo_id,
        photo_type=photo_type,
        file_path=PHOTOS_DIR / f"{stored_photo_id}.bin",
    )
    if not photo.file_path.is_file():
        raise PhotoNotFoundError(f"Photo file not found: {photo_id!r}")
    return photo


def save_photo(file_bytes: bytes, photo_type: PhotoType) -> str:
    """Store image bytes and minimal metadata, returning a unique stable ID."""
    if not isinstance(file_bytes, bytes):
        raise TypeError("file_bytes must be bytes")
    if not isinstance(photo_type, PhotoType):
        raise ValueError("photo_type must be a PhotoType")

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    photo_id = uuid4().hex
    photo = Photo(photo_id=photo_id, photo_type=photo_type, file_path=PHOTOS_DIR / f"{photo_id}.bin")
    photo.file_path.write_bytes(file_bytes)
    _metadata_path(photo_id).write_text(
        json.dumps({"photo_id": photo.photo_id, "photo_type": photo.photo_type.value}),
        encoding="utf-8",
    )
    return photo.photo_id


def get_photo(photo_id: str) -> bytes:
    """Return the original bytes for a locally stored photo ID."""
    return _load_photo(photo_id).file_path.read_bytes()
