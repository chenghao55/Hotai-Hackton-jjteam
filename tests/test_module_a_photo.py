import json

import pytest

from module_a import photo


@pytest.fixture
def photo_store(monkeypatch, tmp_path):
    monkeypatch.setattr(photo, "PHOTOS_DIR", tmp_path / "photos")
    return photo.PHOTOS_DIR


def test_save_photo_stores_bytes_and_returns_unique_id(photo_store):
    image_bytes = b"test-image-bytes"
    photo_id = photo.save_photo(image_bytes, photo.PhotoType.BORROW, "image/jpeg")

    assert photo_id
    assert photo.get_photo(photo_id) == image_bytes
    assert (photo_store / f"{photo_id}.bin").is_file()


def test_saving_identical_bytes_creates_distinct_photo_ids(photo_store):
    first_id = photo.save_photo(b"same-image", photo.PhotoType.BORROW, "image/jpeg")
    second_id = photo.save_photo(b"same-image", photo.PhotoType.BORROW, "image/jpeg")

    assert first_id != second_id
    assert photo.get_photo(first_id) == photo.get_photo(second_id) == b"same-image"


@pytest.mark.parametrize("photo_type", [photo.PhotoType.BORROW, photo.PhotoType.RETURN])
def test_photo_types_are_saved_in_metadata(photo_store, photo_type):
    photo_id = photo.save_photo(b"image", photo_type, "image/png")
    metadata = json.loads((photo_store / f"{photo_id}.json").read_text(encoding="utf-8"))

    assert metadata == {
        "photo_id": photo_id,
        "photo_type": photo_type.value,
        "mime_type": "image/png",
    }


def test_get_photo_info_returns_photo_metadata(photo_store):
    photo_id = photo.save_photo(b"image", photo.PhotoType.RETURN, "image/webp")

    info = photo.get_photo_info(photo_id)

    assert info.photo_id == photo_id
    assert info.photo_type == photo.PhotoType.RETURN
    assert info.mime_type == "image/webp"
    assert info.file_path == photo_store / f"{photo_id}.bin"


def test_missing_photo_id_raises_clear_exception(photo_store):
    with pytest.raises(photo.PhotoNotFoundError, match="Photo not found"):
        photo.get_photo("missing-photo-id")


@pytest.mark.parametrize("file_bytes,photo_type,mime_type,error", [
    (b"image", "borrow", "image/jpeg", ValueError),
    ("image", photo.PhotoType.BORROW, "image/jpeg", TypeError),
    (b"image", photo.PhotoType.BORROW, "", ValueError),
    (b"image", photo.PhotoType.BORROW, "   ", ValueError),
    (b"image", photo.PhotoType.BORROW, None, ValueError),
])
def test_save_photo_validates_its_pure_python_inputs(photo_store, file_bytes, photo_type, mime_type, error):
    with pytest.raises(error):
        photo.save_photo(file_bytes, photo_type, mime_type)
