import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import photos as photo_routes
from backend.schemas.photos import (
    GuidanceAction,
    GuidanceCode,
    GuidanceLevel,
    PhotoCheck,
    PhotoGuidanceResponse,
)
from backend.services.photo_guidance import PhotoGuidanceService


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(photo_routes.router)
    return app


def upload(
    client: TestClient,
    content: bytes = b"image-bytes",
    *,
    capture_slot: str = "front_left",
    entry_side: str | None = None,
):
    data = {
        "photo_type": "return",
        "capture_slot": capture_slot,
        "vehicle_type": "sedan",
        "session_id": "capture-session",
        "frame_id": "1",
    }
    if entry_side is not None:
        data["entry_side"] = entry_side
    return client.post(
        "/photo-guidance",
        data=data,
        files={"file": ("frame.jpg", content, "image/jpeg")},
    )


def test_stub_guidance_returns_pass_without_photo_id(app):
    with TestClient(app) as client:
        response = upload(client)

    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "check": {
            "level": "PASS",
            "code": "PASS",
            "message": "視角正確，請保持穩定並按下快門。",
            "action": "accept",
        },
    }
    assert "photo_id" not in response.json()


def test_rejected_guidance_is_a_successful_http_response(app):
    class BlurryFrameService(PhotoGuidanceService):
        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
            return PhotoGuidanceResponse(
                accepted=False,
                check=PhotoCheck(
                    level=GuidanceLevel.L2,
                    code=GuidanceCode.BLUR,
                    message="畫面模糊，請重新對焦。",
                    action=GuidanceAction.RESHOOT,
                ),
            )

    app.dependency_overrides[photo_routes.get_photo_guidance_service] = BlurryFrameService
    with TestClient(app) as client:
        response = upload(client)

    assert response.status_code == 200
    assert response.json() == {
        "accepted": False,
        "check": {
            "level": "L2",
            "code": "BLUR",
            "message": "畫面模糊，請重新對焦。",
            "action": "reshoot",
        },
    }


def test_empty_file_is_a_validation_error(app):
    with TestClient(app) as client:
        response = upload(client, b"")

    assert response.status_code == 422
    assert response.json()["detail"] == "image file must not be empty"


def test_route_passes_uploaded_bytes_to_service(app):
    class RecordingService(PhotoGuidanceService):
        received: bytes | None = None

        received_context = None

        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
            self.received = image
            self.received_context = context
            return PhotoGuidanceResponse(
                accepted=True,
                check=PhotoCheck(
                    level=GuidanceLevel.PASS,
                    code=GuidanceCode.PASS,
                    message="ok",
                    action=GuidanceAction.ACCEPT,
                ),
            )

    service = RecordingService()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = lambda: service
    with TestClient(app) as client:
        response = upload(client, b"camera-frame")

    assert response.status_code == 200
    assert service.received == b"camera-frame"
    assert service.received_context.mode.value == "preview"
    assert service.received_context.source.value == "camera_raw"
    assert service.received_context.image_mirrored is False


def test_missing_file_is_a_request_error(app):
    with TestClient(app) as client:
        response = client.post("/photo-guidance")

    assert response.status_code == 422


def test_stub_service_is_replaceable(app):
    class ReplacementService(PhotoGuidanceService):
        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
            return PhotoGuidanceResponse(
                accepted=False,
                check=PhotoCheck(
                    level=GuidanceLevel.L3,
                    code=GuidanceCode.TOO_FAR,
                    message="Move closer.",
                    action=GuidanceAction.GUIDE,
                ),
            )

    app.dependency_overrides[photo_routes.get_photo_guidance_service] = ReplacementService
    with TestClient(app) as client:
        response = upload(client)

    assert response.json()["check"]["code"] == "TOO_FAR"


def test_interior_guidance_requires_entry_side(app):
    with TestClient(app) as client:
        missing = upload(client, capture_slot="interior_front")
        accepted = upload(client, capture_slot="interior_front", entry_side="left")

    assert missing.status_code == 422
    assert missing.json()["detail"] == "entry_side is required for interior photos"
    assert accepted.status_code == 200


def test_exterior_guidance_rejects_entry_side(app):
    with TestClient(app) as client:
        response = upload(client, entry_side="left")

    assert response.status_code == 422
    assert response.json()["detail"] == "entry_side is only valid for interior photos"


def test_guidance_rejects_blank_session_id(app):
    with TestClient(app) as client:
        response = client.post(
            "/photo-guidance",
            data={
                "photo_type": "return",
                "capture_slot": "front_left",
                "vehicle_type": "sedan",
                "session_id": "   ",
                "frame_id": "1",
            },
            files={"file": ("frame.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "session_id must not be blank"
