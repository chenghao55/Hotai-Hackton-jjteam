"""The batch runner must keep private source paths out of its report."""

from io import BytesIO

import numpy as np
from PIL import Image

from module_a import photo as photo_storage
from module_a.evaluation.evaluate_pairs import evaluate_manifest


class Detector:
    def predict(self, image):
        return [{"class_id": 0, "confidence": 0.95,
                 "box": [0.08, 0.12, 0.92, 0.88]}]


def test_batch_report_uses_candidate_ids_and_restores_storage(tmp_path):
    rng = np.random.default_rng(1234)
    pixels = np.full((384, 512, 3), 220, dtype=np.uint8)
    pixels[55:340, 42:470] = rng.integers(
        40, 190, size=(285, 428, 3), dtype=np.uint8)
    buffer = BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    source = tmp_path / "private-source.png"
    source.write_bytes(buffer.getvalue())
    manifest = {"rows": [{"candidate_id": "pair-1", "source_group": "local",
                          "capture_slot": "front_left", "borrow_path": str(source),
                          "return_path": str(source), "filename_status": "candidate"}]}
    previous = photo_storage.PHOTOS_DIR

    results = evaluate_manifest(manifest, Detector())

    assert len(results) == 1
    assert results[0]["status"] == "comparable"
    assert results[0]["hotspot_count"] == 0
    assert "borrow_path" not in results[0]
    assert "return_path" not in results[0]
    assert photo_storage.PHOTOS_DIR == previous
