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
from backend.services.photo_guidance import PhotoGuidanceService, ModuleAPhotoGuidanceService
from backend.services.photo_storage import PhotoStorageService
from module_a import CaptureSlot, PhotoType, GuidanceResult


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
    entry_side: str | None = None,
):
    data = {
        "photo_type": photo_type,
        "capture_slot": capture_slot,
        "vehicle_type": "sedan",
        "session_id": "capture-session",
        "frame_id": "2",
    }
    if entry_side is not None:
        data["entry_side"] = entry_side
    return client.post(
        "/photos",
        data=data,
        files={"file": ("photo.jpg", content, "image/jpeg")},
    )


def force_save(
    client: TestClient,
    content: bytes = b"image-bytes",
    photo_type: str = "return",
    capture_slot: str = "front_left",
    entry_side: str | None = None,
):
    data = {
        "photo_type": photo_type,
        "capture_slot": capture_slot,
        "vehicle_type": "sedan",
        "session_id": "capture-session",
        "frame_id": "2",
    }
    if entry_side is not None:
        data["entry_side"] = entry_side
    return client.post(
        "/dev/photos/force-save",
        data=data,
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
        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
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
        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
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


def test_development_force_save_is_disabled_by_default(app):
    class UnexpectedStorage(PhotoStorageService):
        def save(self, *args):
            raise AssertionError("disabled endpoint must not save")

        def get(self, photo_id):
            raise AssertionError("not used")

    app.dependency_overrides[photo_routes.get_photo_storage_service] = UnexpectedStorage
    with TestClient(app) as client:
        response = force_save(client)

    assert response.status_code == 404


def test_development_force_save_stores_real_image_without_calling_guidance(app, monkeypatch):
    class RecordingStorage(PhotoStorageService):
        calls: list[tuple[bytes, PhotoType, CaptureSlot, str]] = []

        def save(self, image, photo_type, capture_slot, mime_type) -> str:
            self.calls.append((image, photo_type, capture_slot, mime_type))
            return "stored-by-module-a"

        def get(self, photo_id):
            raise AssertionError("not used")

    storage = RecordingStorage()
    monkeypatch.setenv("HOTAI_ENABLE_DEV_FORCE_SAVE", "1")
    app.dependency_overrides[photo_routes.get_photo_storage_service] = lambda: storage
    with TestClient(app) as client:
        response = force_save(client, b"rejected-final-image")

    assert response.status_code == 200
    assert response.json() == {"photo_id": "stored-by-module-a"}
    assert storage.calls == [
        (b"rejected-final-image", PhotoType.RETURN, CaptureSlot.FRONT_LEFT, "image/jpeg")
    ]


def test_empty_photo_is_rejected_before_services_are_called(app):
    class UnexpectedService(PhotoGuidanceService):
        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
            raise AssertionError("empty images must not reach guidance")

    app.dependency_overrides[photo_routes.get_photo_guidance_service] = UnexpectedService
    with TestClient(app) as client:
        response = upload(client, b"")

    assert response.status_code == 422
    assert response.json()["detail"] == "image file must not be empty"


def test_uploaded_bytes_are_passed_to_guidance_service(app):
    class RecordingGuidance(PhotoGuidanceService):
        received: bytes | None = None
        received_context = None

        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
            self.received = image
            self.received_context = context
            return rejected_response()

    guidance = RecordingGuidance()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = lambda: guidance
    with TestClient(app) as client:
        response = upload(client, b"final-frame")

    assert response.status_code == 200
    assert guidance.received == b"final-frame"
    assert guidance.received_context.mode.value == "final"
    assert guidance.received_context.source.value == "uploaded_photo"
    assert guidance.received_context.image_mirrored is False


def test_invalid_photo_type_is_a_request_validation_error(app):
    with TestClient(app) as client:
        response = upload(client, photo_type="sideways")

    assert response.status_code == 422


def test_invalid_capture_slot_is_a_request_validation_error(app):
    with TestClient(app) as client:
        response = upload(client, capture_slot="not-a-slot")

    assert response.status_code == 422


def test_interior_upload_requires_entry_side(app):
    from backend.services.photo_guidance import StubPhotoGuidanceService
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = StubPhotoGuidanceService
    with TestClient(app) as client:
        missing = upload(client, capture_slot="interior_rear")
        accepted = upload(client, capture_slot="interior_rear", entry_side="left")

    assert missing.status_code == 422
    assert missing.json()["detail"] == "entry_side is required for interior photos"
    assert accepted.status_code == 200


def test_return_other_damage_is_passed_to_storage(app):
    class AcceptingGuidance(PhotoGuidanceService):
        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
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
        def analyze(self, image: bytes, context) -> PhotoGuidanceResponse:
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


def test_final_capture_rechecks_with_context_and_does_not_store_rejected_image(app):
    class Coach:
        context = None

        def analyze(self, image, context):
            self.context = context
            return GuidanceResult(False, "L6", "TEMPLATE_NOT_CALIBRATED", "構圖基準尚未校正",
                                  "reshoot")

    class Storage(PhotoStorageService):
        def save(self, *args):
            raise AssertionError("rejected image must not be stored")

        def get(self, photo_id):
            raise AssertionError("not used")

    coach = Coach()
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = lambda: ModuleAPhotoGuidanceService(coach)
    app.dependency_overrides[photo_routes.get_photo_storage_service] = Storage
    with TestClient(app) as client:
        response = client.post("/photos",
            data={"photo_type": "return", "capture_slot": "front_left", "vehicle_type": "sedan",
                  "session_id": "session", "frame_id": "7"},
            files={"file": ("photo.jpg", b"frame", "image/jpeg")})

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert response.json()["check"]["action"] == "reshoot"
    assert response.json()["photo_id"] is None
    assert coach.context.mode == "final"
