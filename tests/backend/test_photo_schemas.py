import pytest
from pydantic import ValidationError

from backend.schemas.photos import (
    GuidanceAction,
    GuidanceCode,
    GuidanceLevel,
    PhotoCheck,
    PhotoGuidanceResponse,
    PhotoUploadResponse,
)


def rejected_check() -> PhotoCheck:
    return PhotoCheck(
        level=GuidanceLevel.L2,
        code=GuidanceCode.BLUR,
        message="Hold the phone steady and refocus.",
        action=GuidanceAction.RESHOOT,
    )


def passed_check() -> PhotoCheck:
    return PhotoCheck(
        level=GuidanceLevel.PASS,
        code=GuidanceCode.PASS,
        message="Photo is suitable.",
        action=GuidanceAction.ACCEPT,
    )


def test_valid_rejected_guidance_response():
    response = PhotoGuidanceResponse(accepted=False, check=rejected_check())

    assert response.accepted is False
    assert response.check.code == GuidanceCode.BLUR


def test_valid_pass_guidance_response():
    response = PhotoGuidanceResponse(accepted=True, check=passed_check())

    assert response.accepted is True
    assert response.check.action == GuidanceAction.ACCEPT


def test_valid_accepted_upload_response():
    response = PhotoUploadResponse(accepted=True, photo_id="photo-1", check=passed_check())

    assert response.photo_id == "photo-1"


def test_valid_rejected_upload_response():
    response = PhotoUploadResponse(accepted=False, photo_id=None, check=rejected_check())

    assert response.photo_id is None


def test_accepted_upload_requires_photo_id():
    with pytest.raises(ValidationError, match="nonempty photo_id"):
        PhotoUploadResponse(accepted=True, photo_id=None, check=passed_check())


def test_rejected_upload_cannot_have_photo_id():
    with pytest.raises(ValidationError, match="photo_id=None"):
        PhotoUploadResponse(accepted=False, photo_id="photo-1", check=rejected_check())


def test_rejected_response_cannot_declare_pass():
    with pytest.raises(ValidationError, match="cannot declare PASS"):
        PhotoGuidanceResponse(accepted=False, check=passed_check())


def test_accepted_response_requires_pass_check():
    with pytest.raises(ValidationError, match="require a PASS check"):
        PhotoGuidanceResponse(accepted=True, check=rejected_check())


@pytest.mark.parametrize(
    "code",
    [
        "LOW_DETAIL",
        "SUBJECT_NOT_DETECTED",
        "MULTIPLE_SUBJECTS",
        "SUBJECT_NEAR_EDGE",
        "SUBJECT_TOO_SMALL",
        "SUBJECT_TOO_LARGE",
        "POSSIBLE_WRONG_SLOT",
        "MISSING_REQUIRED_FEATURE",
        "GEOMETRY_MISMATCH",
        "AMBIGUOUS_TEMPLATES",
        "UNSUPPORTED_SLOT",
    ],
)
def test_non_manual_module_a_codes_are_supported(code):
    check = PhotoCheck(
        level=GuidanceLevel.L6,
        code=GuidanceCode(code),
        message="Adjust the camera.",
        action=GuidanceAction.RESHOOT,
    )

    assert check.code.value == code


@pytest.mark.parametrize(
    "manual_code",
    ["TEMPLATE_NOT_CALIBRATED", "FRONT_SEAT_EVIDENCE_UNAVAILABLE"],
)
def test_inconclusive_module_a_codes_allow_reshoot(manual_code):
    response = PhotoGuidanceResponse(accepted=False, check=PhotoCheck(
        level=GuidanceLevel.L6, code=GuidanceCode(manual_code),
        message="Unable to confirm composition.", action=GuidanceAction.RESHOOT,
    ))
    assert response.check.code.value == manual_code
