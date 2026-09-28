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
from .guidance import CaptureContext, GuidanceResult, PhotoCoach, load_config
from .coach_image import YoloDetector

__all__ = [
    "CaptureContext", "GuidanceResult", "PhotoCoach", "YoloDetector", "load_config",
    "CaptureSlot",
    "Photo",
    "PhotoNotFoundError",
    "PhotoType",
    "get_photo",
    "get_photo_info",
    "save_photo",
]
