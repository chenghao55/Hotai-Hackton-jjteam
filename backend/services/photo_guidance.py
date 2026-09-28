"""Module E adapter from HTTP capture requests to Module A's photo coach."""

import os
import tempfile
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from module_a import CaptureContext, PhotoCoach, YoloDetector, load_config

from backend.schemas.photos import PhotoCheck, PhotoGuidanceResponse


class PhotoGuidanceService(ABC):
    @abstractmethod
    def analyze(self, image: bytes, context: CaptureContext | None = None) -> PhotoGuidanceResponse:
        raise NotImplementedError


class ModuleAPhotoGuidanceService(PhotoGuidanceService):
    def __init__(self, coach: PhotoCoach | None = None):
        self.coach = coach

    def analyze(self, image: bytes, context: CaptureContext | None = None) -> PhotoGuidanceResponse:
        if context is None:
            raise ValueError("CAPTURE_CONTEXT_REQUIRED")
        result = (self.coach or get_module_a_photo_coach()).analyze(image, context)
        return PhotoGuidanceResponse(
            accepted=result.accepted,
            check=PhotoCheck(level=result.level, code=result.code,
                             message=result.message, action=result.action),
            can_capture=result.can_capture,
            review_required=result.review_required,
            manual_review_remaining_ms=result.manual_review_remaining_ms,
        )


@lru_cache(maxsize=1)
def get_module_a_photo_coach() -> PhotoCoach:
    configured = os.getenv("HOTAI_MODULE_A_CHECKPOINT_PATH")
    checkpoint = Path(configured) if configured else Path.home() / "Downloads" / "best.pt"
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Module A checkpoint not found: {checkpoint}")
    config = load_config()
    device = os.getenv("HOTAI_MODULE_A_DEVICE", "cpu")
    os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(tempfile.gettempdir()) / "hotai-ultralytics"))
    return PhotoCoach(YoloDetector(checkpoint, config, device), config=config)


@lru_cache(maxsize=1)
def get_photo_guidance_service() -> PhotoGuidanceService:
    return ModuleAPhotoGuidanceService()
