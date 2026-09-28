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
    PhotoUploadResponse,
)
from backend.services.photo_guidance import PhotoGuidanceService
from backend.services.photo_storage import PhotoStorageService
from module_a import CaptureSlot, PhotoType


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(photo_routes.router)
    return app


def upload(
    client: TestClient,
    content: bytes = b"image-bytes",
    photo_type: str = "borrow",
    capture_slot: str = "front_left",
):
    return client.post(
        "/photos",
        data={"photo_type": photo_type, "capture_slot": capture_slot},
        files={"file": ("photo.jpg", content, "image/jpeg")},
    )


def pass_response() -> PhotoGuidanceResponse:
    return PhotoGuidanceResponse(
        accepted=True,
        check=PhotoCheck(
            level=GuidanceLevel.PASS,
            code=GuidanceCode.PASS,
            message="Photo is suitable.",
            action=GuidanceAction.ACCEPT,
        ),
    )


def rejected_response() -> PhotoGuidanceResponse:
    return PhotoGuidanceResponse(
        accepted=False,
        check=PhotoCheck(
            level=GuidanceLevel.L2,
            code=GuidanceCode.BLUR,
            message="畫面模糊，請重新對焦。",
            action=GuidanceAction.RESHOOT,
        ),
    )


def test_accepted_photo_is_saved_once_and_returns_photo_id(app):
    class AcceptingGuidance(PhotoGuidanceService):
        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
            return pass_response()

    class RecordingStorage(PhotoStorageService):
        calls: list[tuple[bytes, PhotoType, CaptureSlot, str]] = []

        def save(
            self,
            image: bytes,
            photo_type: PhotoType,
            capture_slot: CaptureSlot,
            mime_type: str,
        ) -> str:
            self.calls.append((image, photo_type, capture_slot, mime_type))
            return "saved-photo-1"

        def get(self, photo_id: str):
            raise AssertionError("upload must not retrieve a photo")

    storage = RecordingStorage()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = AcceptingGuidance
    app.dependency_overrides[photo_routes.get_photo_storage_service] = lambda: storage
    with TestClient(app) as client:
        response = upload(client, b"accepted-image")

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["photo_id"] == "saved-photo-1"
    assert storage.calls == [
        (b"accepted-image", PhotoType.BORROW, CaptureSlot.FRONT_LEFT, "image/jpeg")
    ]
    assert PhotoUploadResponse.model_validate(response.json()).accepted is True


def test_rejected_photo_does_not_call_storage_and_preserves_guidance(app):
    class RejectingGuidance(PhotoGuidanceService):
        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
            return rejected_response()

    class FailingStorage(PhotoStorageService):
        called = False

        def save(self, image, photo_type, capture_slot, mime_type) -> str:
            self.called = True
            raise AssertionError("rejected photos must not be stored")

        def get(self, photo_id: str):
            raise AssertionError("upload must not retrieve a photo")

    storage = FailingStorage()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = RejectingGuidance
    app.dependency_overrides[photo_routes.get_photo_storage_service] = lambda: storage
    with TestClient(app) as client:
        response = upload(client)

    assert response.status_code == 200
    assert response.json() == {
        "accepted": False,
        "photo_id": None,
        "check": {
            "level": "L2",
            "code": "BLUR",
            "message": "畫面模糊，請重新對焦。",
            "action": "reshoot",
        },
    }
    assert storage.called is False
    assert PhotoUploadResponse.model_validate(response.json()).accepted is False


def test_empty_photo_is_rejected_before_services_are_called(app):
    class UnexpectedService(PhotoGuidanceService):
        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
            raise AssertionError("empty images must not reach guidance")

    app.dependency_overrides[photo_routes.get_photo_guidance_service] = UnexpectedService
    with TestClient(app) as client:
        response = upload(client, b"")

    assert response.status_code == 422
    assert response.json()["detail"] == "image file must not be empty"


def test_uploaded_bytes_are_passed_to_guidance_service(app):
    class RecordingGuidance(PhotoGuidanceService):
        received: bytes | None = None

        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
            self.received = image
            return rejected_response()

    guidance = RecordingGuidance()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = lambda: guidance
    with TestClient(app) as client:
        response = upload(client, b"final-frame")

    assert response.status_code == 200
    assert guidance.received == b"final-frame"


def test_invalid_photo_type_is_a_request_validation_error(app):
    with TestClient(app) as client:
        response = upload(client, photo_type="sideways")

    assert response.status_code == 422


def test_invalid_capture_slot_is_a_request_validation_error(app):
    with TestClient(app) as client:
        response = upload(client, capture_slot="not-a-slot")

    assert response.status_code == 422


def test_return_other_damage_is_passed_to_storage(app):
    class AcceptingGuidance(PhotoGuidanceService):
        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
            return pass_response()

    class RecordingStorage(PhotoStorageService):
        received_type: PhotoType | None = None
        received_slot: CaptureSlot | None = None

        def save(self, image, photo_type, capture_slot, mime_type) -> str:
            self.received_type = photo_type
            self.received_slot = capture_slot
            return "return-photo-1"

        def get(self, photo_id: str):
            raise AssertionError("upload must not retrieve a photo")

    storage = RecordingStorage()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = AcceptingGuidance
    app.dependency_overrides[photo_routes.get_photo_storage_service] = lambda: storage
    with TestClient(app) as client:
        response = upload(client, photo_type="return", capture_slot="other_damage")

    assert response.status_code == 200
    assert storage.received_type == PhotoType.RETURN
    assert storage.received_slot == CaptureSlot.OTHER_DAMAGE


def test_borrow_other_damage_domain_error_is_translated_to_422(app):
    class AcceptingGuidance(PhotoGuidanceService):
        def analyze(self, image: bytes) -> PhotoGuidanceResponse:
            return pass_response()

    class RejectingStorage(PhotoStorageService):
        def save(self, image, photo_type, capture_slot, mime_type) -> str:
            raise ValueError("OTHER_DAMAGE is only valid for return photos")

        def get(self, photo_id: str):
            raise AssertionError("upload must not retrieve a photo")

    app.dependency_overrides[photo_routes.get_photo_guidance_service] = AcceptingGuidance
    app.dependency_overrides[photo_routes.get_photo_storage_service] = RejectingStorage
    with TestClient(app) as client:
        response = upload(client, photo_type="borrow", capture_slot="other_damage")

    assert response.status_code == 422
    assert response.json()["detail"] == "OTHER_DAMAGE is only valid for return photos"
