"""Replaceable E adapters for camera-frame shooting guidance."""

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
from module_a import CaptureContext, CaptureSlot, PhotoCoach, PhotoType


class GuidanceMode(str, Enum):
    PREVIEW = "preview"
    FINAL = "final"


class GuidanceImageSource(str, Enum):
    CAMERA_RAW = "camera_raw"


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
    """Inactive adapter for automatic Module A decisions only."""

    _MANUAL_ONLY_CODES = {
        "TEMPLATE_NOT_CALIBRATED",
        "FRONT_SEAT_EVIDENCE_UNAVAILABLE",
    }

    def __init__(self, coach: PhotoCoach):
        self.coach = coach

    def analyze(
        self,
        image: bytes,
        context: PhotoGuidanceContext,
    ) -> PhotoGuidanceResponse:
        if context.source != GuidanceImageSource.CAMERA_RAW:
            raise UnsupportedGuidanceDecisionError(
                "Module A currently accepts only truthful camera_raw provenance"
            )

        result = self.coach.analyze(
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
        if (
            result.review_required
            or (not result.accepted and result.can_capture)
            or result.action == "human_review"
            or result.code in self._MANUAL_ONLY_CODES
        ):
            raise UnsupportedGuidanceDecisionError(
                "Module A returned a decision outside the approved automatic contract"
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


def get_photo_guidance_service() -> PhotoGuidanceService:
    """Active provider remains the stub until Module A activation blockers resolve."""
    return StubPhotoGuidanceService()
