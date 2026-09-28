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
from backend.services.photo_guidance import PhotoGuidanceService, ModuleAPhotoGuidanceService
from module_a import GuidanceResult


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(photo_routes.router)
    return app


def upload(client: TestClient, content: bytes = b"image-bytes"):
    return client.post("/photo-guidance", files={"file": ("frame.jpg", content, "image/jpeg")})


def test_real_guidance_requires_capture_context_without_loading_model(app):
    with TestClient(app) as client:
        response = upload(client)

    assert response.status_code == 422
    assert response.json()["detail"] == "photo_type and capture_slot are required"


def test_real_adapter_receives_context_and_returns_reshoot_advice(app):
    class Coach:
        context = None

        def analyze(self, image, context):
            self.context = context
            return GuidanceResult(False, "L6", "TEMPLATE_NOT_CALIBRATED", "構圖基準尚未校正",
                                  "reshoot")

    coach = Coach()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = lambda: ModuleAPhotoGuidanceService(coach)
    with TestClient(app) as client:
        response = client.post("/photo-guidance",
            data={"photo_type": "return", "capture_slot": "interior_rear",
                  "vehicle_type": "suv", "entry_side": "right", "session_id": "test-session", "frame_id": "3"},
            files={"file": ("frame.jpg", b"frame", "image/jpeg")})

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert response.json()["check"]["action"] == "reshoot"
    assert coach.context.capture_slot.value == "interior_rear"
    assert coach.context.entry_side == "right"
    assert coach.context.frame_id == 3


def test_rejected_guidance_is_a_successful_http_response(app):
    class BlurryFrameService(PhotoGuidanceService):
        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
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

        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
            self.received = image
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


def test_missing_file_is_a_request_error(app):
    with TestClient(app) as client:
        response = client.post("/photo-guidance")

    assert response.status_code == 422


def test_stub_service_is_replaceable(app):
    class ReplacementService(PhotoGuidanceService):
        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
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
