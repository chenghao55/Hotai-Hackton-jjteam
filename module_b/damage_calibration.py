"""Connected-component features and safe linear calibration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite

import numpy as np
from scipy import ndimage

from .damage_segmentation import DAMAGE_CATEGORIES, DAMAGE_PIXEL_CLASSES


FEATURE_PROBABILITY_LEVELS = (0.30, 0.50, 0.70)
MIN_COMPONENT_PIXELS = 16
MAX_COMPONENT_COUNT = 10
COMPONENT_FEATURES = ("largest_area_ratio", "largest_mean", "largest_p95", "component_count")


def _feature_schema() -> tuple[str, ...]:
    names: list[str] = []
    for category in DAMAGE_CATEGORIES:
        for level in FEATURE_PROBABILITY_LEVELS:
            suffix = f"p{int(level * 100):02d}"
            names.extend(f"{category}.{suffix}.{name}" for name in COMPONENT_FEATURES)
        names.extend((f"{category}.global_max", f"{category}.global_p99"))
    return tuple(names)


FEATURE_SCHEMA = _feature_schema()


@dataclass(frozen=True)
class CategoryEvidence:
    area_ratio: float
    mean_probability: float
    confidence: float


@dataclass(frozen=True)
class DamageFeatureResult:
    values: np.ndarray
    evidence: dict[str, CategoryEvidence]


def _component_features(probability_map: np.ndarray, content_mask: np.ndarray, level: float):
    binary = (probability_map >= level) & content_mask
    labelled, count = ndimage.label(binary, structure=np.ones((3, 3), dtype=np.uint8))
    if count == 0:
        return (0.0, 0.0, 0.0, 0.0), None
    sizes = np.bincount(labelled.reshape(-1), minlength=count + 1)
    valid_labels = np.flatnonzero(sizes >= MIN_COMPONENT_PIXELS)
    valid_labels = valid_labels[valid_labels != 0]
    if not len(valid_labels):
        return (0.0, 0.0, 0.0, 0.0), None
    largest_label = int(valid_labels[np.argmax(sizes[valid_labels])])
    selected = probability_map[labelled == largest_label]
    area_ratio = float(selected.size / int(content_mask.sum()))
    mean_probability = float(selected.mean())
    confidence = float(np.quantile(selected, 0.95))
    features = (
        area_ratio,
        mean_probability,
        confidence,
        float(min(len(valid_labels), MAX_COMPONENT_COUNT)),
    )
    return features, CategoryEvidence(area_ratio, mean_probability, confidence)


def extract_damage_features(probabilities, content_mask) -> DamageFeatureResult:
    array = np.asarray(probabilities, dtype=np.float64)
    mask = np.asarray(content_mask, dtype=bool)
    if array.ndim != 3 or array.shape[0] != len(DAMAGE_PIXEL_CLASSES):
        raise ValueError("Damage probabilities must have shape [3, height, width]")
    if mask.shape != array.shape[1:] or not mask.any():
        raise ValueError("Content mask must match the probability map and contain pixels")
    if not np.isfinite(array).all():
        raise ValueError("Damage probabilities must be finite")
    values: list[float] = []
    evidence: dict[str, CategoryEvidence] = {}
    for class_index, category in enumerate(DAMAGE_CATEGORIES, start=1):
        probability_map = array[class_index]
        for level_index, level in enumerate(FEATURE_PROBABILITY_LEVELS):
            features, component = _component_features(probability_map, mask, level)
            values.extend(features)
            if level_index == 0 and component is not None:
                evidence[category] = component
        content_values = probability_map[mask]
        values.extend((float(content_values.max()), float(np.quantile(content_values, 0.99))))
    feature_array = np.asarray(values, dtype=np.float64)
    if len(feature_array) != len(FEATURE_SCHEMA) or not np.isfinite(feature_array).all():
        raise RuntimeError("Damage feature extraction produced an invalid vector")
    return DamageFeatureResult(feature_array, evidence)


@dataclass(frozen=True)
class LinearDamageCalibrator:
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    intercept: float
    threshold: float
    feature_schema: tuple[str, ...]

    def __post_init__(self) -> None:
        length = len(FEATURE_SCHEMA)
        arrays = (self.mean, self.scale, self.coefficients)
        if any(np.asarray(value).shape != (length,) for value in arrays):
            raise ValueError("Calibrator arrays have incompatible shapes")
        if tuple(self.feature_schema) != FEATURE_SCHEMA:
            raise ValueError("Calibrator feature schema is incompatible")
        if not all(np.isfinite(np.asarray(value, dtype=np.float64)).all() for value in arrays):
            raise ValueError("Calibrator parameters must be finite")
        if np.any(np.asarray(self.scale) <= 0):
            raise ValueError("Calibrator scales must be positive")
        if not isfinite(self.intercept) or not isfinite(self.threshold) or not 0 <= self.threshold <= 1:
            raise ValueError("Calibrator intercept and threshold must be finite and valid")

    def score(self, features) -> float:
        values = np.asarray(features, dtype=np.float64)
        if values.shape != (len(FEATURE_SCHEMA),) or not np.isfinite(values).all():
            raise ValueError("Feature vector is incompatible or non-finite")
        standardized = (values - self.mean) / self.scale
        logit = float(np.dot(standardized, self.coefficients) + self.intercept)
        if logit >= 0:
            probability = 1.0 / (1.0 + exp(-logit))
        else:
            exponential = exp(logit)
            probability = exponential / (1.0 + exponential)
        if not isfinite(probability):
            raise ValueError("Calibrator produced a non-finite score")
        return probability


def calibrator_from_checkpoint(raw: object) -> LinearDamageCalibrator:
    if not isinstance(raw, dict):
        raise ValueError("Checkpoint calibration metadata must be an object")
    try:
        return LinearDamageCalibrator(
            mean=np.asarray(raw["mean"], dtype=np.float64),
            scale=np.asarray(raw["scale"], dtype=np.float64),
            coefficients=np.asarray(raw["coefficients"], dtype=np.float64),
            intercept=float(raw["intercept"]),
            threshold=float(raw["threshold"]),
            feature_schema=tuple(raw["feature_schema"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Checkpoint calibration metadata is invalid") from exc
