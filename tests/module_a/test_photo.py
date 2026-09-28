import json

import pytest

from module_a import (
    CaptureSlot,
    PhotoNotFoundError,
    PhotoType,
    get_photo,
    get_photo_info,
    save_photo,
)
from module_a import photo as photo_module


@pytest.fixture(autouse=True)
def isolated_photo_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_module, "PHOTOS_DIR", tmp_path)


@pytest.mark.parametrize("capture_slot", list(CaptureSlot))
def test_capture_slot_round_trips_through_metadata(capture_slot, tmp_path):
    photo_type = (
        PhotoType.RETURN
        if capture_slot == CaptureSlot.OTHER_DAMAGE
        else PhotoType.BORROW
    )

    photo_id = save_photo(
        b"vehicle-image",
        photo_type,
        capture_slot,
        "image/jpeg",
    )

    metadata = json.loads((tmp_path / f"{photo_id}.json").read_text(encoding="utf-8"))
    assert metadata == {
        "photo_id": photo_id,
        "photo_type": photo_type.value,
        "capture_slot": capture_slot.value,
        "mime_type": "image/jpeg",
    }
    info = get_photo_info(photo_id)
    assert info.photo_id == photo_id
    assert info.photo_type == photo_type
    assert info.capture_slot == capture_slot
    assert info.mime_type == "image/jpeg"


def test_return_other_damage_is_allowed():
    photo_id = save_photo(
        b"new-return-damage",
        PhotoType.RETURN,
        CaptureSlot.OTHER_DAMAGE,
        "image/png",
    )

    assert get_photo_info(photo_id).capture_slot == CaptureSlot.OTHER_DAMAGE


def test_borrow_other_damage_is_rejected_before_writing(tmp_path):
    with pytest.raises(ValueError, match="only valid for return photos"):
        save_photo(
            b"invalid-borrow-damage",
            PhotoType.BORROW,
            CaptureSlot.OTHER_DAMAGE,
            "image/jpeg",
        )

    assert list(tmp_path.iterdir()) == []


def test_non_enum_capture_slot_is_rejected():
    with pytest.raises(ValueError, match="capture_slot must be a CaptureSlot"):
        save_photo(
            b"vehicle-image",
            PhotoType.RETURN,
            "front_left",
            "image/jpeg",
        )


def test_invalid_capture_slot_in_stored_metadata_is_rejected(tmp_path):
    photo_id = "invalid-slot"
    (tmp_path / f"{photo_id}.bin").write_bytes(b"vehicle-image")
    (tmp_path / f"{photo_id}.json").write_text(
        json.dumps(
            {
                "photo_id": photo_id,
                "photo_type": "return",
                "capture_slot": "sideways",
                "mime_type": "image/jpeg",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PhotoNotFoundError, match="metadata is invalid"):
        get_photo_info(photo_id)


def test_get_photo_still_returns_original_bytes():
    original = b"\x89PNG\r\nvehicle-image"
    photo_id = save_photo(
        original,
        PhotoType.BORROW,
        CaptureSlot.REAR,
        "image/png",
    )

    assert get_photo(photo_id) == original
