"""Checkpoint loading and review-only inference for the damage segmenter."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from PIL import Image

from .condition_schema import MODEL_STATUS, REVIEW_STATE, SEVERITY_BY_CATEGORY
from .damage_calibration import LinearDamageCalibrator, calibrator_from_checkpoint, extract_damage_features
from .damage_segmentation import (
    DAMAGE_CATEGORIES,
    DAMAGE_PIXEL_CLASSES,
    letterbox_content_mask,
    resize_and_pad_pair,
)
from .dataset import load_rgb_image
from .inference import _resolve_device
from .model import (
    ARCHITECTURE,
    DAMAGE_SEGMENTATION_ARCHITECTURE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_damage_segmentation_model,
    build_shared_visible_damage_head,
    build_model,
    build_transform,
    shared_visible_damage_logits,
)
from .schemas import PhotoConditionResult, PhotoDamageAssessment


DAMAGE_OUTPUT_ORDER = ("collision_damage", "scratch")
DAMAGE_TASK_NAME = "vehicle_damage_segmentation"


@dataclass
class DamageSegmentationBundle:
    model: object
    probability_thresholds: dict[str, float]
    min_area_pixels: dict[str, int]
    model_version: str
    image_size: int
    device: object
    dataset_manifest_sha256: str
    calibrator: LinearDamageCalibrator | None = None
    visible_damage_gate: object | None = None
    visible_damage_threshold: float | None = None
    visible_damage_image_size: int | None = None
    shared_visible_damage_head: object | None = None


def _validate_category_mapping(raw: object, *, value_type: type, name: str):
    if not isinstance(raw, dict) or set(raw) != set(DAMAGE_CATEGORIES):
        raise ValueError(f"Checkpoint {name} must cover exactly the damage categories")
    values = {category: value_type(raw[category]) for category in DAMAGE_CATEGORIES}
    return values


def load_damage_segmentation_model(
    checkpoint_path: str | Path, device: str = "auto"
) -> DamageSegmentationBundle:
    import torch

    resolved_device = _resolve_device(device)
    checkpoint = torch.load(checkpoint_path, map_location=resolved_device, weights_only=True)
    required = {
        "architecture": DAMAGE_SEGMENTATION_ARCHITECTURE,
        "task": DAMAGE_TASK_NAME,
        "status": MODEL_STATUS,
        "review_state": REVIEW_STATE,
    }
    for key, expected in required.items():
        if checkpoint.get(key) != expected:
            raise ValueError(f"Unsupported checkpoint {key}: {checkpoint.get(key)!r}")
    if tuple(checkpoint.get("pixel_classes", ())) != DAMAGE_PIXEL_CLASSES:
        raise ValueError("Checkpoint pixel classes are incompatible")
    thresholds = _validate_category_mapping(
        checkpoint.get("probability_thresholds"), value_type=float, name="probability_thresholds"
    )
    if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in thresholds.values()):
        raise ValueError("Damage probability thresholds must be finite and within [0, 1]")
    min_areas = _validate_category_mapping(
        checkpoint.get("min_area_pixels"), value_type=int, name="min_area_pixels"
    )
    if any(value <= 0 for value in min_areas.values()):
        raise ValueError("Damage minimum areas must be positive")
    image_size = int(checkpoint.get("image_size", 0))
    if image_size <= 0:
        raise ValueError("Checkpoint image_size must be positive")
    model_version = checkpoint.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("Checkpoint model_version must be nonempty")
    manifest_hash = checkpoint.get("dataset_manifest_sha256")
    if not isinstance(manifest_hash, str) or len(manifest_hash) != 64:
        raise ValueError("Checkpoint dataset manifest hash is invalid")

    model = build_damage_segmentation_model(pretrained_backbone=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(resolved_device).eval()
    for parameter in model.parameters():
        parameter.requires_grad = False
    calibration_raw = checkpoint.get("calibration")
    calibrator = (
        calibrator_from_checkpoint(calibration_raw) if calibration_raw is not None else None
    )
    gate_raw = checkpoint.get("visible_damage_gate")
    gate_model = None
    shared_gate_head = None
    gate_threshold = None
    gate_image_size = None
    if gate_raw is not None:
        if not isinstance(gate_raw, dict) or gate_raw.get("architecture") != ARCHITECTURE:
            raise ValueError("Checkpoint visible-damage gate metadata is incompatible")
        gate_threshold = float(gate_raw.get("threshold", float("nan")))
        gate_image_size = int(gate_raw.get("image_size", 0))
        if not isfinite(gate_threshold) or not 0 <= gate_threshold <= 1 or gate_image_size <= 0:
            raise ValueError("Checkpoint visible-damage gate settings are invalid")
        gate_model = build_model(pretrained=False)
        gate_model.load_state_dict(gate_raw["model_state_dict"])
        gate_model.to(resolved_device).eval()
        for parameter in gate_model.parameters():
            parameter.requires_grad = False
    shared_gate_raw = checkpoint.get("shared_visible_damage_gate")
    if shared_gate_raw is not None:
        if gate_raw is not None:
            raise ValueError("Checkpoint cannot contain both standalone and shared damage gates")
        if not isinstance(shared_gate_raw, dict) or shared_gate_raw.get("architecture") != "shared_lraspp_high_pool_linear":
            raise ValueError("Checkpoint shared visible-damage gate metadata is incompatible")
        gate_threshold = float(shared_gate_raw.get("threshold", float("nan")))
        gate_image_size = int(shared_gate_raw.get("image_size", 0))
        if not isfinite(gate_threshold) or not 0 <= gate_threshold <= 1 or gate_image_size <= 0:
            raise ValueError("Checkpoint shared visible-damage gate settings are invalid")
        shared_gate_head = build_shared_visible_damage_head()
        shared_gate_head.load_state_dict(shared_gate_raw["model_state_dict"])
        shared_gate_head.to(resolved_device).eval()
        for parameter in shared_gate_head.parameters():
            parameter.requires_grad = False
    return DamageSegmentationBundle(
        model=model,
        probability_thresholds=thresholds,
        min_area_pixels=min_areas,
        model_version=model_version,
        image_size=image_size,
        device=resolved_device,
        dataset_manifest_sha256=manifest_hash,
        calibrator=calibrator,
        visible_damage_gate=gate_model,
        visible_damage_threshold=gate_threshold,
        visible_damage_image_size=gate_image_size,
        shared_visible_damage_head=shared_gate_head,
    )


def _passes_visible_damage_gate(model_bundle: DamageSegmentationBundle, image) -> bool:
    import torch

    if (
        model_bundle.visible_damage_gate is None
        and model_bundle.shared_visible_damage_head is None
    ):
        return True
    transform = build_transform(
        training=False, image_size=int(model_bundle.visible_damage_image_size)
    )
    tensor = transform(load_rgb_image(image)).unsqueeze(0).to(model_bundle.device)
    with torch.inference_mode():
        if model_bundle.shared_visible_damage_head is not None:
            logit = shared_visible_damage_logits(
                model_bundle.model,
                model_bundle.shared_visible_damage_head,
                tensor,
            )
        else:
            logit = model_bundle.visible_damage_gate(tensor).reshape(-1)
        if len(logit) != 1:
            raise ValueError("Visible-damage gate produced an incompatible output")
        score = float(torch.sigmoid(logit[0]).detach().cpu())
    if not isfinite(score):
        raise ValueError("Visible-damage gate produced a non-finite score")
    return score > float(model_bundle.visible_damage_threshold)


def _damage_tensor(image: str | Path | Image.Image, size: int):
    from torchvision.transforms import functional as functional

    rgb = load_rgb_image(image)
    blank_mask = Image.new("L", rgb.size, 0)
    padded, _ = resize_and_pad_pair(rgb, blank_mask, size)
    return functional.normalize(functional.to_tensor(padded), IMAGENET_MEAN, IMAGENET_STD)


def _damage_inputs(image: str | Path | Image.Image, size: int):
    from torchvision.transforms import functional as functional

    rgb = load_rgb_image(image)
    content_mask = letterbox_content_mask(rgb.size, size)
    blank_mask = Image.new("L", rgb.size, 0)
    padded, _ = resize_and_pad_pair(rgb, blank_mask, size)
    tensor = functional.normalize(functional.to_tensor(padded), IMAGENET_MEAN, IMAGENET_STD)
    return tensor, content_mask


def _predict_probability_map(model_bundle: DamageSegmentationBundle, image):
    import torch

    tensor, content_mask = _damage_inputs(image, model_bundle.image_size)
    tensor = tensor.unsqueeze(0).to(model_bundle.device)
    with torch.inference_mode():
        output = model_bundle.model(tensor)
        logits = output["out"] if isinstance(output, dict) else output
        if tuple(logits.shape[:2]) != (1, len(DAMAGE_PIXEL_CLASSES)):
            raise ValueError("Model produced an incompatible damage logit tensor")
        probabilities = torch.softmax(logits, dim=1)[0].detach().cpu().numpy()
    return probabilities, content_mask


def extract_image_damage_features(model_bundle: DamageSegmentationBundle, image):
    """Run the frozen segmenter and return the versioned calibration features."""
    probabilities, content_mask = _predict_probability_map(model_bundle, image)
    return extract_damage_features(probabilities, content_mask)


def damage_scores_from_probabilities(
    probabilities, thresholds: dict[str, float], min_area_pixels: dict[str, int]
) -> dict[str, float]:
    """Aggregate pixel probabilities into image findings using a minimum area gate."""
    import numpy as np

    array = np.asarray(probabilities)
    if array.ndim != 3 or array.shape[0] != len(DAMAGE_PIXEL_CLASSES):
        raise ValueError("Model produced an incompatible damage probability tensor")
    if not np.isfinite(array).all():
        raise ValueError("Model produced non-finite damage probabilities")
    scores: dict[str, float] = {}
    for class_index, category in enumerate(DAMAGE_CATEGORIES, start=1):
        selected = array[class_index][array[class_index] > thresholds[category]]
        if selected.size >= min_area_pixels[category]:
            scores[category] = float(np.quantile(selected, 0.95))
    return scores


def predict_damage_conditions(
    model_bundle: DamageSegmentationBundle,
    image: str | Path | Image.Image,
    photo_id: str,
) -> list[PhotoConditionResult]:
    if not isinstance(photo_id, str) or not photo_id.strip():
        raise ValueError("photo_id must be a nonempty string")
    if not _passes_visible_damage_gate(model_bundle, image):
        return []
    probabilities, content_mask = _predict_probability_map(model_bundle, image)
    if model_bundle.calibrator is None:
        scores = damage_scores_from_probabilities(
            probabilities,
            model_bundle.probability_thresholds,
            model_bundle.min_area_pixels,
        )
    else:
        feature_result = extract_damage_features(probabilities, content_mask)
        if not feature_result.evidence:
            scores = {}
        else:
            damage_score = model_bundle.calibrator.score(feature_result.values)
            scores = (
                {
                    category: evidence.confidence
                    for category, evidence in feature_result.evidence.items()
                }
                if damage_score > model_bundle.calibrator.threshold
                else {}
            )
    return [
        PhotoConditionResult(
            photo_id=photo_id,
            category=category,
            severity=SEVERITY_BY_CATEGORY[category],
            confidence=scores[category],
            review_state=REVIEW_STATE,
            model_version=model_bundle.model_version,
        )
        for category in DAMAGE_OUTPUT_ORDER
        if category in scores
    ]


def predict_damage_assessment(
    model_bundle: DamageSegmentationBundle,
    image: str | Path | Image.Image,
    photo_id: str,
) -> PhotoDamageAssessment:
    """Return the image-level state and damage findings used by downstream code."""
    detections = tuple(predict_damage_conditions(model_bundle, image, photo_id))
    detected = bool(detections)
    return PhotoDamageAssessment(
        photo_id=photo_id,
        damage_state="damage_detected" if detected else "no_detected_damage",
        claim_candidate="claim_candidate" if detected else "no_claim_candidate",
        detections=detections,
        review_state=REVIEW_STATE,
        model_version=model_bundle.model_version,
    )
