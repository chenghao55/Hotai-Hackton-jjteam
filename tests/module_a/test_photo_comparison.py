"""Comparison core tests use synthetic texture to verify data flow only."""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image, ImageDraw

from module_a import CaptureSlot, PhotoType, save_photo
from module_a import photo as photo_module
from module_a.photo_comparison import compare_stored_photos


@pytest.fixture(autouse=True)
def isolated_photo_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_module, "PHOTOS_DIR", tmp_path)


class SingleCarDetector:
    def predict(self, image):
        return [{"class_id": 0, "confidence": 0.95,
                 "box": [0.08, 0.12, 0.92, 0.88]}]


def _photo(changed=False):
    rng = np.random.default_rng(1234)
    pixels = np.full((384, 512, 3), 220, dtype=np.uint8)
    pixels[55:340, 42:470] = rng.integers(
        40, 190, size=(285, 428, 3), dtype=np.uint8)
    image = Image.fromarray(pixels)
    if changed:
        ImageDraw.Draw(image).rectangle((240, 160, 295, 215), fill=(240, 240, 240))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _pair(changed=False, borrow_slot=CaptureSlot.FRONT_LEFT, return_slot=None):
    if return_slot is None:
        return_slot = borrow_slot
    borrow_id = save_photo(_photo(), PhotoType.BORROW,
                           borrow_slot, "image/png")
    return_id = save_photo(_photo(changed), PhotoType.RETURN,
                           return_slot, "image/png")
    return borrow_id, return_id


def test_compare_stored_pair_reports_hotspot_in_return_coordinates():
    borrow_id, return_id = _pair(changed=True)

    result = compare_stored_photos(borrow_id, return_id,
                                   detector=SingleCarDetector())

    assert result.status == "comparable"
    assert result.reason is None
    assert result.heatmap_png.startswith(b"\x89PNG")
    assert result.comparison_mask_png.startswith(b"\x89PNG")
    assert result.heatmap_size == (512, 384)
    assert result.return_image_size == (512, 384)
    assert 0 < result.analysis_coverage_ratio <= result.overlap_ratio
    assert result.overlap_ratio > 0.5
    assert any(x1 <= 265 < x2 and y1 <= 185 < y2
               for x1, y1, x2, y2 in (spot.box for spot in result.hotspots))
    with Image.open(BytesIO(result.comparison_mask_png)) as mask:
        assert mask.mode == "L"
        assert mask.size == result.heatmap_size
        assert mask.getpixel((265, 185)) == 255
        assert mask.getpixel((0, 0)) == 0
    with Image.open(BytesIO(result.heatmap_png)) as heatmap:
        assert heatmap.mode == "RGBA"
        assert heatmap.getpixel((0, 0))[3] == 0
        assert heatmap.getpixel((265, 185))[3] > 0


def test_compare_stored_pair_rejects_wrong_slot_before_image_work():
    borrow_id, return_id = _pair(return_slot=CaptureSlot.FRONT_RIGHT)

    with pytest.raises(ValueError, match="PAIR_INVALID"):
        compare_stored_photos(borrow_id, return_id, detector=SingleCarDetector())


@pytest.mark.parametrize("slot", [CaptureSlot.FRONT_LEFT,
                                  CaptureSlot.FRONT_RIGHT,
                                  CaptureSlot.REAR_LEFT,
                                  CaptureSlot.REAR_RIGHT])
def test_identical_pair_has_no_change_hotspot(slot):
    borrow_id, return_id = _pair(borrow_slot=slot)

    result = compare_stored_photos(borrow_id, return_id,
                                   detector=SingleCarDetector())

    assert result.status == "comparable"
    assert result.hotspots == ()


def test_ambiguous_subject_cannot_produce_heatmap():
    borrow_id, return_id = _pair()

    class NoCarDetector:
        def predict(self, image):
            return []

    result = compare_stored_photos(borrow_id, return_id,
                                   detector=NoCarDetector())

    assert result.status == "not_comparable"
    assert result.reason == "BORROW_SUBJECT_UNCERTAIN"
    assert result.heatmap_png is None


def test_compare_stored_pair_reports_unusable_return_photo():
    borrow_id = save_photo(_photo(), PhotoType.BORROW,
                           CaptureSlot.FRONT_LEFT, "image/png")
    return_id = save_photo(b"not an image", PhotoType.RETURN,
                           CaptureSlot.FRONT_LEFT, "image/png")

    result = compare_stored_photos(borrow_id, return_id,
                                   detector=SingleCarDetector())

    assert result.status == "not_comparable"
    assert result.reason == "RETURN_IMAGE_UNUSABLE"
    assert result.hotspots == ()
    assert result.heatmap_png is None
    assert result.comparison_mask_png is None


def test_missing_borrow_baseline_has_explicit_reason():
    return_id = save_photo(_photo(), PhotoType.RETURN,
                           CaptureSlot.FRONT_LEFT, "image/png")

    result = compare_stored_photos("missing", return_id,
                                   detector=SingleCarDetector())

    assert result.status == "not_comparable"
    assert result.reason == "BORROW_BASELINE_UNAVAILABLE"
    assert result.capture_slot is None


def test_matches_confined_to_one_small_patch_do_not_validate_whole_car():
    rng = np.random.default_rng(9)
    pixels = np.full((384, 512, 3), 220, dtype=np.uint8)
    pixels[155:235, 200:310] = rng.integers(
        0, 255, size=(80, 110, 3), dtype=np.uint8)
    output = BytesIO()
    Image.fromarray(pixels).save(output, format="PNG")
    borrow_id = save_photo(output.getvalue(), PhotoType.BORROW,
                           CaptureSlot.FRONT_LEFT, "image/png")
    return_id = save_photo(output.getvalue(), PhotoType.RETURN,
                           CaptureSlot.FRONT_LEFT, "image/png")

    result = compare_stored_photos(borrow_id, return_id,
                                   detector=SingleCarDetector())

    assert result.status == "not_comparable"
    assert result.reason == "ALIGNMENT_LOCALIZED"
    assert result.heatmap_png is None
