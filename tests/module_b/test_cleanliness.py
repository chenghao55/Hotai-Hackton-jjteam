from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from module_b import CleanlinessEvidence, PhotoCleanlinessAssessment
from module_b.cleanliness_dataset import (
    CleanlinessSegmentationDataset,
    discover_mola_vi_samples,
    split_cleanliness_samples,
)
from module_b.cleanliness_inference import cleanliness_evidence_from_probabilities


def test_cleanliness_schema_serializes_dirty_evidence():
    result = PhotoCleanlinessAssessment(
        photo_id="interior-1",
        cleanliness_state="dirty",
        confidence=0.82,
        evidence=(CleanlinessEvidence("stain", 0.82, 32),),
        review_state="needs_review",
        model_version="interior-cleanliness-v1",
    )

    assert result.to_dict() == {
        "photo_id": "interior-1",
        "cleanliness_state": "dirty",
        "confidence": 0.82,
        "evidence": [{"type": "stain", "confidence": 0.82, "area_pixels": 32}],
        "review_state": "needs_review",
        "model_version": "interior-cleanliness-v1",
    }


def test_cleanliness_schema_rejects_clean_state_with_evidence():
    with pytest.raises(ValueError, match="must match"):
        PhotoCleanlinessAssessment(
            photo_id="interior-1",
            cleanliness_state="no_visible_dirt_detected",
            confidence=0.8,
            evidence=(CleanlinessEvidence("dirt", 0.8, 16),),
            review_state="needs_review",
            model_version="v1",
        )


def test_probability_aggregation_uses_area_gate_and_fixed_order():
    probabilities = np.zeros((3, 8, 8), dtype=np.float32)
    probabilities[0] = 0.1
    probabilities[1, :2, :] = 0.8
    probabilities[2, 4:8, :] = 0.9
    mask = np.ones((8, 8), dtype=bool)

    evidence, score = cleanliness_evidence_from_probabilities(
        probabilities,
        mask,
        {"stain": 0.5, "dirt": 0.5},
        {"stain": 16, "dirt": 16},
    )

    assert [item.type for item in evidence] == ["dirt", "stain"]
    assert [item.area_pixels for item in evidence] == [32, 16]
    assert score == pytest.approx(0.9)


def test_probability_aggregation_rejects_non_finite_output():
    probabilities = np.zeros((3, 4, 4), dtype=np.float32)
    probabilities[1, 0, 0] = np.nan

    with pytest.raises(ValueError, match="finite"):
        cleanliness_evidence_from_probabilities(
            probabilities,
            np.ones((4, 4), dtype=bool),
            {"stain": 0.5, "dirt": 0.5},
            {"stain": 1, "dirt": 1},
        )


def jpeg_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (8, 6), "white").save(stream, format="JPEG")
    return stream.getvalue()


def _write_mola_pair(root, vehicle_id, view, filename, *, stain, dirt):
    image_path = root / "IMAGES" / vehicle_id / view / filename
    mask_path = root / "SEGMENTATIONS" / vehicle_id / view / filename
    image_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 10), "white").save(image_path)
    mask = np.zeros((10, 20), dtype=np.uint8)
    if stain:
        mask[:5, :5] = 4
    if dirt:
        mask[5:, 5:10] = 5
    Image.fromarray(mask, mode="L").save(mask_path, format="PNG")


def test_mola_discovery_maps_stain_and_dirt_and_preserves_vehicle_groups(tmp_path):
    cars = []
    for vehicle_number in range(1, 4):
        vehicle_id = f"CAR{vehicle_number:04d}"
        files = []
        for name, stain, dirt in (
            ("clean.jpg", False, False),
            ("stain.jpg", True, False),
            ("dirt.jpg", False, True),
        ):
            _write_mola_pair(
                tmp_path, vehicle_id, "P1", name, stain=stain, dirt=dirt
            )
            files.append(name)
        cars.append(
            {
                "FullName": vehicle_id,
                "Images": [
                    {"View": "P1", "Files": files, "Segmentations": files}
                ],
            }
        )
    (tmp_path / "dataset.json").write_text(
        __import__("json").dumps({"Cars": cars}), encoding="utf-8"
    )

    samples = discover_mola_vi_samples(tmp_path)
    train, validation, locked = split_cleanliness_samples(
        samples, seed=20260914, validation_fraction=0.2, test_fraction=0.2
    )

    assert len(samples) == 9
    assert {sample.labels for sample in samples} == {(0, 0), (1, 0), (0, 1)}
    groups = [{sample.group_id for sample in split} for split in (train, validation, locked)]
    assert groups[0].isdisjoint(groups[1])
    assert groups[0].isdisjoint(groups[2])
    assert groups[1].isdisjoint(groups[2])


def test_mola_dataset_returns_aligned_rgb_tensor_and_class_mask(tmp_path):
    _write_mola_pair(
        tmp_path, "CAR0001", "P1", "sample.jpg", stain=True, dirt=True
    )
    (tmp_path / "dataset.json").write_text(
        '{"Cars":[{"FullName":"CAR0001","Images":[{"View":"P1",'
        '"Files":["sample.jpg"],"Segmentations":["sample.jpg"]}]}]}',
        encoding="utf-8",
    )
    sample = discover_mola_vi_samples(tmp_path)[0]

    image, mask, index = CleanlinessSegmentationDataset(
        [sample], training=False, image_size=32
    )[0]

    assert tuple(image.shape) == (3, 32, 32)
    assert tuple(mask.shape) == (32, 32)
    assert set(mask.unique().tolist()) == {0, 1, 2}
    assert index == 0

    augmented_image, augmented_mask, _ = CleanlinessSegmentationDataset(
        [sample], training=True, image_size=32
    )[0]
    assert tuple(augmented_image.shape) == (3, 32, 32)
    assert tuple(augmented_mask.shape) == (32, 32)
    assert set(augmented_mask.unique().tolist()).issubset({0, 1, 2})
