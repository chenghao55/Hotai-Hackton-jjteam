from dataclasses import replace
from pathlib import Path

import pytest

from backend.services.photo_guidance import (
    GuidanceImageSource,
    GuidanceMode,
    ModuleAPhotoGuidanceService,
    PhotoGuidanceContext,
    StubPhotoGuidanceService,
    UnsupportedGuidanceDecisionError,
    get_module_a_checkpoint_path,
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
        result(action="human_review"),
    ],
)
def test_adapter_rejects_unresolved_manual_decisions(decision):
    with pytest.raises(UnsupportedGuidanceDecisionError):
        ModuleAPhotoGuidanceService(Coach(decision)).analyze(b"frame", context())


def test_adapter_rejects_unknown_or_gallery_provenance():
    with pytest.raises(UnsupportedGuidanceDecisionError, match="provenance"):
        ModuleAPhotoGuidanceService(Coach(result())).analyze(
            b"gallery-file",
            replace(context(), source=None),
        )


def test_active_provider_uses_real_coach():
    assert isinstance(get_photo_guidance_service(), ModuleAPhotoGuidanceService)


def test_checkpoint_path_defaults_to_the_repository_artifact(monkeypatch):
    monkeypatch.delenv("HOTAI_MODULE_A_CHECKPOINT_PATH", raising=False)

    assert get_module_a_checkpoint_path() == (
        Path(__file__).resolve().parents[2] / "artifacts" / "module_a" / "best.pt"
    )


def test_checkpoint_path_preserves_explicit_override(monkeypatch, tmp_path):
    override = tmp_path / "override.pt"
    monkeypatch.setenv("HOTAI_MODULE_A_CHECKPOINT_PATH", str(override))

    assert get_module_a_checkpoint_path() == override


def test_uncalibrated_template_is_a_reshoot_result():
    response = ModuleAPhotoGuidanceService(Coach(result(code="TEMPLATE_NOT_CALIBRATED", level="L6"))).analyze(b"frame", context())
    assert response.accepted is False
    assert response.check.code.value == "TEMPLATE_NOT_CALIBRATED"


def test_final_upload_preserves_provenance_and_rechecks():
    coach = Coach(result())
    ModuleAPhotoGuidanceService(coach).analyze(b"final", replace(context(), mode=GuidanceMode.FINAL, source=GuidanceImageSource.UPLOADED_PHOTO))
    assert coach.received[0] == b"final"
    assert coach.received[1].source == "uploaded_photo"
    assert coach.received[1].mode == "final"


def test_uploaded_photo_is_not_valid_preview_provenance():
    with pytest.raises(UnsupportedGuidanceDecisionError):
        ModuleAPhotoGuidanceService(Coach(result())).analyze(b"frame", replace(context(), source=GuidanceImageSource.UPLOADED_PHOTO))


@pytest.mark.parametrize("slot", [CaptureSlot.FUEL_PARKING_CARD, CaptureSlot.OTHER_DAMAGE, CaptureSlot.REAR])
def test_uncoached_slots_validate_image_without_loading_model(monkeypatch, slot):
    from io import BytesIO
    from PIL import Image
    from backend.services import photo_guidance as service
    def unexpected():
        raise AssertionError("uncoached slots must not load YOLO")
    monkeypatch.setattr(service, "get_module_a_photo_coach", unexpected)
    buffer = BytesIO()
    Image.new("RGB", (32, 32)).save(buffer, format="JPEG")
    response = ModuleAPhotoGuidanceService().analyze(buffer.getvalue(), replace(context(), capture_slot=slot, entry_side=None))
    assert response.accepted
    assert "格式有效" in response.check.message


def test_invalid_image_decoder_does_not_use_optional_model_plugins(monkeypatch):
    from PIL import Image, UnidentifiedImageError
    from module_a.coach_image import decode
    def unexpected(*args, **kwargs):
        raise AssertionError("must use the format-restricted decoder")
    monkeypatch.setattr(Image, "open", unexpected)
    with pytest.raises(UnidentifiedImageError):
        decode(b"not-an-image")
