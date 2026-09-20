"""Pure-Python local photo storage for Modules A and B."""

from .photo import Photo, PhotoNotFoundError, PhotoType, get_photo, save_photo

__all__ = [
    "Photo",
    "PhotoNotFoundError",
    "PhotoType",
    "get_photo",
    "save_photo",
]
