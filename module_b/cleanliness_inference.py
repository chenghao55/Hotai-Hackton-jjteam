"""Checkpoint loading and single-photo inference for interior cleanliness."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from PIL import Image

from .condition_schema import MODEL_STATUS, REVIEW_STATE
from .damage_segmentation import letterbox_content_mask, resize_and_pad_pair
from .dataset import load_rgb_image
from .inference import _resolve_device
from .model import (
    CLEANLINESS_SEGMENTATION_ARCHITECTURE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_cleanliness_segmentation_model,
)
from .schemas import CleanlinessEvidence, PhotoCleanlinessAssessment


CLEANLINESS_TASK_NAME = "vehicle_interior_cleanliness_segmentation"
CLEANLINESS_PIXEL_CLASSES = ("background", "stain", "dirt")
CLEANLINESS_CATEGORIES = ("stain", "dirt")
CLEANLINESS_OUTPUT_ORDER = ("dirt", "stain")


@dataclass
class CleanlinessModelBundle:
    model: object
    probability_thresholds: dict[str, float]
    min_area_pixels: dict[str, int]
    model_version: str
    image_size: int
    device: object
    dataset_manifest_sha256: str
    status: str


def _category_mapping(raw: object, *, value_type: type, name: str):
    if not isinstance(raw, dict) or set(raw) != set(CLEANLINESS_CATEGORIES):
        raise ValueError(f"Checkpoint {name} must cover exactly stain and dirt")
    return {category: value_type(raw[category]) for category in CLEANLINESS_CATEGORIES}


def load_cleanliness_model(
    checkpoint_path: str | Path, device: str = "auto"
) -> CleanlinessModelBundle:
    import torch

    resolved_device = _resolve_device(device)
    checkpoint = torch.load(checkpoint_path, map_location=resolved_device, weights_only=True)
    required = {
        "architecture": CLEANLINESS_SEGMENTATION_ARCHITECTURE,
        "task": CLEANLINESS_TASK_NAME,
        "review_state": REVIEW_STATE,
    }
    for key, expected in required.items():
        if checkpoint.get(key) != expected:
            raise ValueError(f"Unsupported checkpoint {key}: {checkpoint.get(key)!r}")
    status = checkpoint.get("status")
    if status not in {MODEL_STATUS, "external_only_review_only"}:
        raise ValueError(f"Unsupported checkpoint status: {status!r}")
    if tuple(checkpoint.get("pixel_classes", ())) != CLEANLINESS_PIXEL_CLASSES:
        raise ValueError("Checkpoint pixel classes are incompatible")
    thresholds = _category_mapping(
        checkpoint.get("probability_thresholds"),
        value_type=float,
        name="probability_thresholds",
    )
    if any(not isfinite(value) or not 0 <= value <= 1 for value in thresholds.values()):
        raise ValueError("Cleanliness thresholds must be finite and within [0, 1]")
    min_areas = _category_mapping(
        checkpoint.get("min_area_pixels"), value_type=int, name="min_area_pixels"
    )
    if any(value <= 0 for value in min_areas.values()):
        raise ValueError("Cleanliness minimum areas must be positive")
    image_size = int(checkpoint.get("image_size", 0))
    if image_size <= 0:
        raise ValueError("Checkpoint image_size must be positive")
    model_version = checkpoint.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("Checkpoint model_version must be nonempty")
    manifest_hash = checkpoint.get("dataset_manifest_sha256")
    if not isinstance(manifest_hash, str) or len(manifest_hash) != 64:
        raise ValueError("Checkpoint dataset manifest hash is invalid")

    model = build_cleanliness_segmentation_model(pretrained_backbone=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(resolved_device).eval()
    for parameter in model.parameters():
        parameter.requires_grad = False
    return CleanlinessModelBundle(
        model=model,
        probability_thresholds=thresholds,
        min_area_pixels=min_areas,
        model_version=model_version,
        image_size=image_size,
        device=resolved_device,
        dataset_manifest_sha256=manifest_hash,
        status=status,
    )


def _inputs(image: str | Path | Image.Image, size: int):
    from torchvision.transforms import functional as functional

    rgb = load_rgb_image(image)
    content_mask = letterbox_content_mask(rgb.size, size)
    padded, _ = resize_and_pad_pair(rgb, Image.new("L", rgb.size, 0), size)
    tensor = functional.normalize(functional.to_tensor(padded), IMAGENET_MEAN, IMAGENET_STD)
    return tensor, content_mask


def _probabilities(bundle: CleanlinessModelBundle, image):
    import numpy as np
    import torch

    tensor, content_mask = _inputs(image, bundle.image_size)
    with torch.inference_mode():
        output = bundle.model(tensor.unsqueeze(0).to(bundle.device))
        logits = output["out"] if isinstance(output, dict) else output
        if tuple(logits.shape[:2]) != (1, len(CLEANLINESS_PIXEL_CLASSES)):
            raise ValueError("Model produced an incompatible cleanliness logit tensor")
        probabilities = torch.softmax(logits, dim=1)[0].detach().cpu().numpy()
    if not np.isfinite(probabilities).all():
        raise ValueError("Model produced non-finite cleanliness probabilities")
    return probabilities, content_mask


def cleanliness_evidence_from_probabilities(
    probabilities,
    content_mask,
    thresholds: dict[str, float],
    min_area_pixels: dict[str, int],
) -> tuple[tuple[CleanlinessEvidence, ...], float]:
    """Aggregate foreground pixels and return evidence plus an uncalibrated dirty score."""
    import numpy as np

    array = np.asarray(probabilities)
    mask = np.asarray(content_mask, dtype=bool)
    if array.ndim != 3 or array.shape[0] != len(CLEANLINESS_PIXEL_CLASSES):
        raise ValueError("Cleanliness probabilities have an incompatible shape")
    if mask.shape != tuple(array.shape[1:]):
        raise ValueError("Cleanliness content mask has an incompatible shape")
    if not np.isfinite(array).all():
        raise ValueError("Cleanliness probabilities must be finite")

    by_category: dict[str, CleanlinessEvidence] = {}
    category_scores: list[float] = []
    for class_index, category in enumerate(CLEANLINESS_CATEGORIES, start=1):
        values = array[class_index][mask]
        score = float(np.quantile(values, 0.995)) if values.size else 0.0
        category_scores.append(score)
        selected = values[values > thresholds[category]]
        if selected.size >= min_area_pixels[category]:
            by_category[category] = CleanlinessEvidence(
                type=category,
                confidence=float(np.quantile(selected, 0.95)),
                area_pixels=int(selected.size),
            )
    evidence = tuple(
        by_category[category]
        for category in CLEANLINESS_OUTPUT_ORDER
        if category in by_category
    )
    return evidence, max(category_scores, default=0.0)


def predict_cleanliness(
    model_bundle: CleanlinessModelBundle,
    image: str | Path | Image.Image,
    photo_id: str,
) -> PhotoCleanlinessAssessment:
    if not isinstance(photo_id, str) or not photo_id.strip():
        raise ValueError("photo_id must be a nonempty string")
    probabilities, content_mask = _probabilities(model_bundle, image)
    evidence, dirty_score = cleanliness_evidence_from_probabilities(
        probabilities,
        content_mask,
        model_bundle.probability_thresholds,
        model_bundle.min_area_pixels,
    )
    dirty = bool(evidence)
    confidence = dirty_score if dirty else 1.0 - dirty_score
    return PhotoCleanlinessAssessment(
        photo_id=photo_id,
        cleanliness_state="dirty" if dirty else "no_visible_dirt_detected",
        confidence=float(min(1.0, max(0.0, confidence))),
        evidence=evidence,
        review_state=REVIEW_STATE,
        model_version=model_bundle.model_version,
    )
