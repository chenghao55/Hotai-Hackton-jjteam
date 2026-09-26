"""Pure-Python local photo storage for Modules A and B."""

from .photo import (
    CaptureSlot,
    Photo,
    PhotoNotFoundError,
    PhotoType,
    get_photo,
    get_photo_info,
    save_photo,
)

__all__ = [
    "CaptureSlot",
    "Photo",
    "PhotoNotFoundError",
    "PhotoType",
    "get_photo",
    "get_photo_info",
    "save_photo",
]
