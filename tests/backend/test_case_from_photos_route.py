from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import cases as case_routes
from backend.services.photo_storage import PhotoStorageNotFoundError, PhotoStorageService
from backend.state.cases import cases
from module_a import CaptureSlot, Photo, PhotoType
from module_b import ModuleB
from module_d import Case, ConditionCategory, Detection, ReviewState, Severity


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(case_routes.router)
    cases.clear()
    yield application
    application.dependency_overrides.clear()
    cases.clear()


def photo_info(photo_id: str) -> Photo:
    return Photo(
        photo_id=photo_id,
        photo_type=PhotoType.RETURN,
        capture_slot=CaptureSlot.OTHER_DAMAGE,
        mime_type="image/jpeg",
        file_path=Path(f"{photo_id}.bin"),
    )


class RecordingStorage(PhotoStorageService):
    def __init__(self, images: dict[str, bytes]) -> None:
        self.images = images
        self.received_ids: list[str] = []

    def save(self, image, photo_type, capture_slot, mime_type) -> str:
        raise AssertionError("Case creation must not save photos")

    def get(self, photo_id: str) -> tuple[bytes, Photo]:
        self.received_ids.append(photo_id)
        try:
            return self.images[photo_id], photo_info(photo_id)
        except KeyError as exc:
            raise PhotoStorageNotFoundError("missing") from exc


class RecordingModuleB(ModuleB):
    def __init__(self, result: Callable[[str], Case] | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, list[tuple[str, bytes]]]] = []

    def analyze(self, case_id: str, photos: list[tuple[str, bytes]]) -> Case:
        self.calls.append((case_id, photos))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result(case_id)


def post_case_from_photos(client: TestClient, photo_ids=None):
    return client.post(
        "/cases/from-photos",
        json={"photo_ids": photo_ids or ["photo-1", "photo-2"]},
    )


def test_create_case_from_photos_loads_bytes_calls_b_and_stores_case(app):
    storage = RecordingStorage({"photo-1": b"borrow-bytes", "photo-2": b"return-bytes"})
    def created(case_id: str) -> Case:
        return Case(
            case_id,
            [
                Detection(
                    detection_id="detection-1",
                    borrow_photo_id="photo-1",
                    return_photo_id="photo-2",
                    source_photo_id="photo-2",
                    category=ConditionCategory.SCRATCH,
                    severity=Severity.MINOR,
                    confidence=0.5,
                    review_state=ReviewState.NEEDS_REVIEW,
                )
            ],
            priority_score=20,
        )

    module_b = RecordingModuleB(created)
    app.dependency_overrides[case_routes.get_photo_storage_service] = lambda: storage
    app.dependency_overrides[case_routes.get_case_building_module_b_provider] = lambda: lambda: module_b

    with TestClient(app) as client:
        response = post_case_from_photos(client)

    assert response.status_code == 201
    generated_case_id = response.json()["case_id"]
    assert UUID(generated_case_id).version == 4
    assert response.json()["priority_score"] == 20
    assert storage.received_ids == ["photo-1", "photo-2"]
    assert module_b.calls == [
        (generated_case_id, [("photo-1", b"borrow-bytes"), ("photo-2", b"return-bytes")])
    ]
    assert cases == {generated_case_id: created(generated_case_id)}


def test_missing_photo_returns_404_without_calling_module_b_or_creating_case(app):
    storage = RecordingStorage({"photo-1": b"image"})
    module_b = RecordingModuleB(Case)
    app.dependency_overrides[case_routes.get_photo_storage_service] = lambda: storage
    app.dependency_overrides[case_routes.get_case_building_module_b_provider] = lambda: lambda: module_b

    with TestClient(app) as client:
        response = post_case_from_photos(client)

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown photo_id: 'photo-2'"}
    assert module_b.calls == []
    assert cases == {}


def test_module_b_validation_error_is_422_and_case_state_remains_atomic(app):
    storage = RecordingStorage({"photo-1": b"borrow", "photo-2": b"return"})
    module_b = RecordingModuleB(ValueError("missing matching borrow photo"))
    existing = Case("existing")
    cases[existing.case_id] = existing
    app.dependency_overrides[case_routes.get_photo_storage_service] = lambda: storage
    app.dependency_overrides[case_routes.get_case_building_module_b_provider] = lambda: lambda: module_b

    with TestClient(app) as client:
        response = post_case_from_photos(client)

    assert response.status_code == 422
    assert response.json() == {"detail": "missing matching borrow photo"}
    assert len(module_b.calls) == 1
    generated_case_id, analyzed_photos = module_b.calls[0]
    assert UUID(generated_case_id).version == 4
    assert analyzed_photos == [("photo-1", b"borrow"), ("photo-2", b"return")]
    assert cases == {"existing": existing}


def test_generated_case_id_retries_on_collision(app, monkeypatch):
    storage = RecordingStorage({"photo-1": b"borrow", "photo-2": b"return"})
    module_b = RecordingModuleB(Case)
    existing_case_id = "00000000-0000-4000-8000-000000000001"
    generated_case_id = "00000000-0000-4000-8000-000000000002"
    cases[existing_case_id] = Case(existing_case_id)
    generated_ids = iter([UUID(existing_case_id), UUID(generated_case_id)])
    monkeypatch.setattr(case_routes, "uuid4", lambda: next(generated_ids))
    app.dependency_overrides[case_routes.get_photo_storage_service] = lambda: storage
    app.dependency_overrides[case_routes.get_case_building_module_b_provider] = lambda: lambda: module_b

    with TestClient(app) as client:
        response = post_case_from_photos(client)

    assert response.status_code == 201
    assert response.json()["case_id"] == generated_case_id
    assert storage.received_ids == ["photo-1", "photo-2"]
    assert module_b.calls[0][0] == generated_case_id


@pytest.mark.parametrize(
    "payload",
    [
        {"photo_ids": []},
        {"photo_ids": ["photo-1", "photo-1"]},
        {"photo_ids": [" "]},
        {"case_id": "client-generated-id", "photo_ids": ["photo-1"]},
    ],
)
def test_invalid_request_is_rejected_before_dependencies_are_called(app, payload):
    with TestClient(app) as client:
        response = client.post("/cases/from-photos", json=payload)

    assert response.status_code == 422
