"""Public output contracts for Module B."""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal

from .condition_schema import REVIEW_STATE, SEVERITY_BY_CATEGORY


@dataclass(frozen=True)
class PhotoClaimResult:
    """A single image's model score and thresholded claim label."""

    photo_id: str
    claim_probability: float
    predicted_label: Literal["claim", "no_claim"]
    model_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.photo_id, str) or not self.photo_id.strip():
            raise ValueError("photo_id must be a nonempty string")
        if (
            type(self.claim_probability) is not float
            or not isfinite(self.claim_probability)
            or not 0.0 <= self.claim_probability <= 1.0
        ):
            raise ValueError("claim_probability must be a finite float within [0, 1]")
        if self.predicted_label not in {"claim", "no_claim"}:
            raise ValueError("predicted_label must be 'claim' or 'no_claim'")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("model_version must be a nonempty string")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PhotoConditionResult:
    """One review-only condition finding emitted for a single image."""

    photo_id: str
    category: Literal["scratch", "collision_damage"]
    severity: Literal["minor", "moderate", "severe"]
    confidence: float
    review_state: Literal["needs_review"]
    model_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.photo_id, str) or not self.photo_id.strip():
            raise ValueError("photo_id must be a nonempty string")
        if self.category not in SEVERITY_BY_CATEGORY:
            raise ValueError("category must be a supported condition category")
        if self.severity != SEVERITY_BY_CATEGORY[self.category]:
            raise ValueError("severity must match the fixed category mapping")
        if (
            type(self.confidence) is not float
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("confidence must be a finite float within [0, 1]")
        if self.review_state != REVIEW_STATE:
            raise ValueError("condition results must use review_state='needs_review'")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("model_version must be a nonempty string")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PhotoDamageAssessment:
    """Image-level damage state plus zero or more concrete damage findings."""

    photo_id: str
    damage_state: Literal["damage_detected", "no_detected_damage"]
    claim_candidate: Literal["claim_candidate", "no_claim_candidate"]
    detections: tuple[PhotoConditionResult, ...]
    review_state: Literal["needs_review"]
    model_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.photo_id, str) or not self.photo_id.strip():
            raise ValueError("photo_id must be a nonempty string")
        expected_candidate = (
            "claim_candidate" if self.damage_state == "damage_detected" else "no_claim_candidate"
        )
        if self.damage_state not in {"damage_detected", "no_detected_damage"}:
            raise ValueError("damage_state must be a supported image-level state")
        if self.claim_candidate != expected_candidate:
            raise ValueError("claim_candidate must match damage_state")
        if not isinstance(self.detections, tuple) or any(
            not isinstance(item, PhotoConditionResult) for item in self.detections
        ):
            raise ValueError("detections must be a tuple of PhotoConditionResult objects")
        if (self.damage_state == "damage_detected") != bool(self.detections):
            raise ValueError("damage_state must match whether detections are present")
        if any(
            item.photo_id != self.photo_id or item.model_version != self.model_version
            for item in self.detections
        ):
            raise ValueError("nested detections must match the assessment identity")
        if self.review_state != REVIEW_STATE:
            raise ValueError("damage assessments must use review_state='needs_review'")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("model_version must be a nonempty string")

    def to_dict(self) -> dict[str, object]:
        return {
            "photo_id": self.photo_id,
            "damage_state": self.damage_state,
            "claim_candidate": self.claim_candidate,
            "detections": [item.to_dict() for item in self.detections],
            "review_state": self.review_state,
            "model_version": self.model_version,
        }


@dataclass(frozen=True)
class CleanlinessEvidence:
    """One localized type of visible vehicle-interior cleanliness issue."""

    type: Literal["stain", "dirt"]
    confidence: float
    area_pixels: int

    def __post_init__(self) -> None:
        if self.type not in {"stain", "dirt"}:
            raise ValueError("cleanliness evidence type must be 'stain' or 'dirt'")
        if (
            type(self.confidence) is not float
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("confidence must be a finite float within [0, 1]")
        if type(self.area_pixels) is not int or self.area_pixels <= 0:
            raise ValueError("area_pixels must be a positive integer")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PhotoCleanlinessAssessment:
    """Single-photo visible dirt/stain assessment from the interior model."""

    photo_id: str
    cleanliness_state: Literal["dirty", "no_visible_dirt_detected"]
    confidence: float
    evidence: tuple[CleanlinessEvidence, ...]
    review_state: Literal["needs_review"]
    model_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.photo_id, str) or not self.photo_id.strip():
            raise ValueError("photo_id must be a nonempty string")
        if self.cleanliness_state not in {"dirty", "no_visible_dirt_detected"}:
            raise ValueError("cleanliness_state is unsupported")
        if (
            type(self.confidence) is not float
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("confidence must be a finite float within [0, 1]")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, CleanlinessEvidence) for item in self.evidence
        ):
            raise ValueError("evidence must be a tuple of CleanlinessEvidence objects")
        if (self.cleanliness_state == "dirty") != bool(self.evidence):
            raise ValueError("cleanliness_state must match whether evidence is present")
        if self.review_state != REVIEW_STATE:
            raise ValueError("cleanliness assessments must use review_state='needs_review'")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("model_version must be a nonempty string")

    def to_dict(self) -> dict[str, object]:
        return {
            "photo_id": self.photo_id,
            "cleanliness_state": self.cleanliness_state,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
            "review_state": self.review_state,
            "model_version": self.model_version,
        }
