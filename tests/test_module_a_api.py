import pytest
from fastapi.testclient import TestClient

from module_d import api
from module_a import get_photo, get_photo_info
from module_a import photo as photo_module


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(photo_module, "PHOTOS_DIR", tmp_path / "photos")
    with TestClient(api.app) as test_client:
        yield test_client


@pytest.mark.parametrize("photo_type", ["borrow", "return"])
def test_upload_photo_stores_bytes_and_returns_id(client, photo_type):
    image_bytes = b"small-image-test-bytes"

    response = client.post(
        "/photos",
        data={"photo_type": photo_type},
        files={"file": ("vehicle.jpg", image_bytes, "image/jpeg")},
    )

    assert response.status_code == 201
    photo_id = response.json()["photo_id"]
    assert get_photo(photo_id) == image_bytes
    assert get_photo_info(photo_id).mime_type == "image/jpeg"
    assert get_photo_info(photo_id).photo_type.value == photo_type


def test_upload_without_file_content_type_returns_422(client):
    boundary = "module-a-test-boundary"
    body = (
        f"--{boundary}\r\n"
        "Content-Disposition: form-data; name=\"photo_type\"\r\n\r\n"
        "borrow\r\n"
        f"--{boundary}\r\n"
        "Content-Disposition: form-data; name=\"file\"; filename=\"vehicle.bin\"\r\n\r\n"
        "bytes\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    response = client.post(
        "/photos",
        content=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 422


def test_get_photo_returns_original_bytes_and_saved_content_type(client):
    upload = client.post(
        "/photos",
        data={"photo_type": "return"},
        files={"file": ("vehicle.png", b"png-bytes", "image/png")},
    )
    photo_id = upload.json()["photo_id"]

    response = client.get(f"/photos/{photo_id}")

    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-type"] == "image/png"


def test_missing_photo_returns_404(client):
    response = client.get("/photos/missing-photo")

    assert response.status_code == 404
    assert "Photo not found" in response.json()["detail"]


@pytest.mark.parametrize("failure", ["missing_file", "invalid_metadata"])
def test_unreadable_stored_photo_returns_404(client, failure):
    upload = client.post(
        "/photos",
        data={"photo_type": "borrow"},
        files={"file": ("vehicle.jpg", b"bytes", "image/jpeg")},
    )
    photo_id = upload.json()["photo_id"]
    if failure == "missing_file":
        (photo_module.PHOTOS_DIR / f"{photo_id}.bin").unlink()
    else:
        (photo_module.PHOTOS_DIR / f"{photo_id}.json").write_text("not-json", encoding="utf-8")

    response = client.get(f"/photos/{photo_id}")

    assert response.status_code == 404


def test_photo_api_does_not_change_case_store(client):
    before = dict(api.cases)
    client.post(
        "/photos",
        data={"photo_type": "borrow"},
        files={"file": ("vehicle.jpg", b"bytes", "image/jpeg")},
    )
    assert api.cases == before
