from dataclasses import replace

import pytest

from backend.services.photo_guidance import (
    GuidanceImageSource,
    GuidanceMode,
    ModuleAPhotoGuidanceService,
    PhotoGuidanceContext,
    StubPhotoGuidanceService,
    UnsupportedGuidanceDecisionError,
    get_photo_guidance_service,
)
from backend.schemas.photos import EntrySide, VehicleType
from module_a import CaptureSlot, GuidanceResult, PhotoType


class Coach:
    def __init__(self, result: GuidanceResult):
        self.result = result
        self.received = None

    def analyze(self, image, context):
        self.received = (image, context)
        return self.result


def context() -> PhotoGuidanceContext:
    return PhotoGuidanceContext(
        photo_type=PhotoType.RETURN,
        capture_slot=CaptureSlot.INTERIOR_FRONT,
        vehicle_type=VehicleType.SEDAN,
        session_id="session-1",
        frame_id=7,
        entry_side=EntrySide.LEFT,
        mode=GuidanceMode.PREVIEW,
        image_mirrored=False,
        source=GuidanceImageSource.CAMERA_RAW,
    )


def result(**changes) -> GuidanceResult:
    base = GuidanceResult(
        accepted=False,
        level="L3",
        code="SUBJECT_TOO_SMALL",
        message="請稍微靠近。",
        action="reshoot",
    )
    return replace(base, **changes)


def test_adapter_maps_automatic_pass_without_internal_fields():
    coach = Coach(result(accepted=True, level="PASS", code="PASS", action="accept"))
    response = ModuleAPhotoGuidanceService(coach).analyze(b"frame", context())

    assert response.model_dump() == {
        "accepted": True,
        "check": {
            "level": "PASS",
            "code": "PASS",
            "message": "請稍微靠近。",
            "action": "accept",
        },
    }
    _, received = coach.received
    assert received.photo_type == PhotoType.RETURN
    assert received.capture_slot == CaptureSlot.INTERIOR_FRONT
    assert received.entry_side == "left"
    assert received.mode == "preview"
    assert received.source == "camera_raw"


def test_adapter_maps_ordinary_blocking_guidance():
    response = ModuleAPhotoGuidanceService(Coach(result())).analyze(b"frame", context())

    assert response.accepted is False
    assert response.check.code.value == "SUBJECT_TOO_SMALL"
    assert response.check.action.value == "reshoot"


@pytest.mark.parametrize(
    "decision",
    [
        result(review_required=True),
        result(can_capture=True),
        result(action="human_review"),
        result(code="TEMPLATE_NOT_CALIBRATED", level="L6"),
    ],
)
def test_adapter_rejects_unresolved_manual_decisions(decision):
    with pytest.raises(UnsupportedGuidanceDecisionError):
        ModuleAPhotoGuidanceService(Coach(decision)).analyze(b"frame", context())


def test_adapter_rejects_unknown_or_gallery_provenance():
    with pytest.raises(UnsupportedGuidanceDecisionError, match="camera_raw"):
        ModuleAPhotoGuidanceService(Coach(result())).analyze(
            b"gallery-file",
            replace(context(), source=None),
        )


def test_active_provider_remains_stub():
    assert isinstance(get_photo_guidance_service(), StubPhotoGuidanceService)
