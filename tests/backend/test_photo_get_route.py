from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import photos as photo_routes
from backend.services.photo_guidance import PhotoGuidanceService
from backend.services.photo_storage import PhotoStorageNotFoundError, PhotoStorageService
from module_a import Photo, PhotoType


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(photo_routes.router)
    return app


def stored_photo(photo_id: str = "photo-1") -> tuple[bytes, Photo]:
    return (
        b"\x89PNG\r\nbinary-image",
        Photo(photo_id, PhotoType.BORROW, "image/png", Path(f"{photo_id}.bin")),
    )


def test_existing_photo_returns_original_binary_bytes(app):
    class ExistingStorage(PhotoStorageService):
        def save(self, image, photo_type, mime_type):
            raise AssertionError("GET must not save a photo")

        def get(self, photo_id):
            return stored_photo(photo_id)

    app.dependency_overrides[photo_routes.get_photo_storage_service] = ExistingStorage
    with TestClient(app) as client:
        response = client.get("/photos/photo-1")

    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\nbinary-image"
    assert response.headers["content-type"] == "image/png"


def test_route_passes_requested_photo_id_to_storage(app):
    class RecordingStorage(PhotoStorageService):
        received_id: str | None = None

        def save(self, image, photo_type, mime_type):
            raise AssertionError("GET must not save a photo")

        def get(self, photo_id):
            self.received_id = photo_id
            return stored_photo(photo_id)

    storage = RecordingStorage()
    app.dependency_overrides[photo_routes.get_photo_storage_service] = lambda: storage
    with TestClient(app) as client:
        response = client.get("/photos/requested-id")

    assert response.status_code == 200
    assert storage.received_id == "requested-id"


def test_missing_photo_is_translated_to_404(app):
    class MissingStorage(PhotoStorageService):
        def save(self, image, photo_type, mime_type):
            raise AssertionError("GET must not save a photo")

        def get(self, photo_id):
            raise PhotoStorageNotFoundError("internal storage detail")

    app.dependency_overrides[photo_routes.get_photo_storage_service] = MissingStorage
    with TestClient(app) as client:
        response = client.get("/photos/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown photo_id: 'missing'"}


def test_get_route_does_not_call_guidance_service(app):
    class ExistingStorage(PhotoStorageService):
        def save(self, image, photo_type, mime_type):
            raise AssertionError("GET must not save a photo")

        def get(self, photo_id):
            return stored_photo(photo_id)

    class UnexpectedGuidance(PhotoGuidanceService):
        called = False

        def analyze(self, image):
            self.called = True
            raise AssertionError("GET must not invoke guidance")

    guidance = UnexpectedGuidance()
    app.dependency_overrides[photo_routes.get_photo_storage_service] = ExistingStorage
    app.dependency_overrides[photo_routes.get_photo_guidance_service] = lambda: guidance
    with TestClient(app) as client:
        response = client.get("/photos/photo-1")

    assert response.status_code == 200
    assert guidance.called is False


def test_binary_response_is_not_json_or_base64(app):
    class ExistingStorage(PhotoStorageService):
        def save(self, image, photo_type, mime_type):
            raise AssertionError("GET must not save a photo")

        def get(self, photo_id):
            return stored_photo(photo_id)

    app.dependency_overrides[photo_routes.get_photo_storage_service] = ExistingStorage
    with TestClient(app) as client:
        response = client.get("/photos/photo-1")

    assert response.headers["content-type"] != "application/json"
    assert response.content.startswith(b"\x89PNG")
