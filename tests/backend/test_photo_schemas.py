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
