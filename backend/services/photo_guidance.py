"""Replaceable E adapters for camera-frame shooting guidance."""

import os
import tempfile
from pathlib import Path
from functools import lru_cache
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from backend.schemas.photos import (
    EntrySide,
    GuidanceAction,
    GuidanceCode,
    GuidanceLevel,
    PhotoCheck,
    PhotoGuidanceResponse,
    VehicleType,
)
from module_a import CaptureContext, CaptureSlot, PhotoCoach, PhotoType, YoloDetector, load_config
from module_a.coach_image import decode
from module_a.guidance import SLOTS


class GuidanceMode(str, Enum):
    PREVIEW = "preview"
    FINAL = "final"


class GuidanceImageSource(str, Enum):
    CAMERA_RAW = "camera_raw"
    UPLOADED_PHOTO = "uploaded_photo"


@dataclass(frozen=True)
class PhotoGuidanceContext:
    photo_type: PhotoType
    capture_slot: CaptureSlot
    vehicle_type: VehicleType
    session_id: str
    frame_id: int
    entry_side: EntrySide | None
    mode: GuidanceMode
    image_mirrored: bool = False
    source: GuidanceImageSource | None = None


class UnsupportedGuidanceDecisionError(RuntimeError):
    """A result or image provenance is outside the approved E product contract."""


class PhotoGuidanceService(ABC):
    """Analyzes image bytes and returns the HTTP guidance contract."""

    @abstractmethod
    def analyze(
        self,
        image: bytes,
        context: PhotoGuidanceContext,
    ) -> PhotoGuidanceResponse:
        raise NotImplementedError


class StubPhotoGuidanceService(PhotoGuidanceService):
    """Temporary PASS result until Module A supplies its guidance adapter."""

    def analyze(
        self,
        image: bytes,
        context: PhotoGuidanceContext,
    ) -> PhotoGuidanceResponse:
        return PhotoGuidanceResponse(
            accepted=True,
            check=PhotoCheck(
                level=GuidanceLevel.PASS,
                code=GuidanceCode.PASS,
                message="視角正確，請保持穩定並按下快門。",
                action=GuidanceAction.ACCEPT,
            ),
        )


class ModuleAPhotoGuidanceService(PhotoGuidanceService):
    """Active adapter; preview guides, final upload accepts or requests a reshoot."""

    def __init__(self, coach: PhotoCoach | None = None):
        self.coach = coach

    def analyze(
        self,
        image: bytes,
        context: PhotoGuidanceContext,
    ) -> PhotoGuidanceResponse:
        if context.source != GuidanceImageSource.CAMERA_RAW and not (
            context.mode == GuidanceMode.FINAL
            and context.source == GuidanceImageSource.UPLOADED_PHOTO
        ):
            raise UnsupportedGuidanceDecisionError("Unsupported image provenance")

        if context.capture_slot not in SLOTS:
            decode(image)
            return PhotoGuidanceResponse(accepted=True, check=PhotoCheck(
                level=GuidanceLevel.PASS, code=GuidanceCode.PASS,
                message="此類照片不適用車角 AI 構圖檢核；照片格式有效，可以拍攝。",
                action=GuidanceAction.ACCEPT,
            ))

        result = (self.coach or get_module_a_photo_coach()).analyze(
            image,
            CaptureContext(
                photo_type=context.photo_type,
                capture_slot=context.capture_slot,
                vehicle_type=context.vehicle_type.value,
                session_id=context.session_id,
                frame_id=context.frame_id,
                entry_side=context.entry_side.value if context.entry_side else None,
                mode=context.mode.value,
                image_mirrored=context.image_mirrored,
                source=context.source.value,
            ),
        )
        try:
            level = GuidanceLevel(result.level)
            code = GuidanceCode(result.code)
            action = GuidanceAction(result.action)
        except ValueError as exc:
            raise UnsupportedGuidanceDecisionError(
                "Module A returned an unsupported guidance value"
            ) from exc

        return PhotoGuidanceResponse(
            accepted=result.accepted,
            check=PhotoCheck(
                level=level,
                code=code,
                message=result.message,
                action=action,
            ),
        )


def get_module_a_checkpoint_path() -> Path:
    """Resolve the trusted Module A checkpoint without machine-specific defaults."""
    override = os.getenv("HOTAI_MODULE_A_CHECKPOINT_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "artifacts" / "module_a" / "best.pt"


@lru_cache(maxsize=1)
def get_module_a_photo_coach() -> PhotoCoach:
    checkpoint = get_module_a_checkpoint_path()
    if not checkpoint.is_file():
        raise FileNotFoundError("Module A checkpoint is unavailable")
    config = load_config()
    os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(tempfile.gettempdir()) / "hotai-ultralytics"))
    try:
        detector = YoloDetector(checkpoint, config, os.getenv("HOTAI_MODULE_A_DEVICE", "cpu"))
    except Exception as exc:
        raise RuntimeError("Module A model could not be loaded") from exc
    return PhotoCoach(detector, config=config)


def get_photo_guidance_service() -> PhotoGuidanceService:
    """Use the real coach; loading the checkpoint is deferred until a coached request."""
    return ModuleAPhotoGuidanceService()
