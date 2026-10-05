"""Replaceable AI-analysis contracts and the deployed damage-model adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from module_d.models import ConditionCategory, Severity

if TYPE_CHECKING:
    from .cleanliness_inference import CleanlinessModelBundle
    from .damage_inference import DamageSegmentationBundle


@dataclass(frozen=True)
class AIFinding:
    """One vehicle-condition finding produced from one source photo."""

    detection_id: str
    source_photo_id: str
    category: ConditionCategory
    severity: Severity
    confidence: float


class AIAnalyzer(ABC):
    """Dependency implemented by a concrete AI or computer-vision model."""

    @abstractmethod
    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        raise NotImplementedError


class DamageModelAnalyzer(AIAnalyzer):
    """Adapt the deployed single-photo damage model to the backend contract."""

    def __init__(self, model_bundle: DamageSegmentationBundle) -> None:
        from .damage_inference import DamageSegmentationBundle

        if not isinstance(model_bundle, DamageSegmentationBundle):
            raise TypeError("model_bundle must be a DamageSegmentationBundle")
        self._model_bundle = model_bundle

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str | Path,
        *,
        device: str = "auto",
    ) -> DamageModelAnalyzer:
        from .damage_inference import load_damage_segmentation_model

        return cls(load_damage_segmentation_model(checkpoint_path, device=device))

    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        """photo: list[tuple(id, binary file)]"""
        
        from .damage_inference import predict_damage_conditions

        if not isinstance(photos, list):
            raise TypeError("photos must be a list of (photo_id, bytes) pairs")

        findings: list[AIFinding] = []
        for photo in photos:
            if not isinstance(photo, tuple) or len(photo) != 2:
                raise ValueError("photos must contain only (photo_id, bytes) pairs")
            photo_id, image_bytes = photo
            if not isinstance(photo_id, str) or not photo_id.strip():
                raise ValueError("photo_id must be a nonempty string")
            if not isinstance(image_bytes, bytes):
                raise TypeError("photo bytes must be bytes")

            results = predict_damage_conditions(
                self._model_bundle,
                BytesIO(image_bytes),
                photo_id=photo_id,
            )

            findings.extend(
                AIFinding(
                    detection_id=f"{photo_id}:{result.category}",
                    source_photo_id=photo_id,
                    category=ConditionCategory(result.category),
                    severity=Severity(result.severity),
                    confidence=result.confidence,
                )
                for result in results
            )
        return findings


class CleanlinessModelAnalyzer(AIAnalyzer):
    """Adapt the single-photo interior-cleanliness model to `AIFinding`."""

    def __init__(self, model_bundle: CleanlinessModelBundle) -> None:
        from .cleanliness_inference import CleanlinessModelBundle

        if not isinstance(model_bundle, CleanlinessModelBundle):
            raise TypeError("model_bundle must be a CleanlinessModelBundle")
        self._model_bundle = model_bundle

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str | Path,
        *,
        device: str = "auto",
    ) -> CleanlinessModelAnalyzer:
        from .cleanliness_inference import load_cleanliness_model

        return cls(load_cleanliness_model(checkpoint_path, device=device))

    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        from .cleanliness_inference import predict_cleanliness

        if not isinstance(photos, list):
            raise TypeError("photos must be a list of (photo_id, bytes) pairs")
        findings: list[AIFinding] = []
        for photo in photos:
            if not isinstance(photo, tuple) or len(photo) != 2:
                raise ValueError("photos must contain only (photo_id, bytes) pairs")
            photo_id, image_bytes = photo
            if not isinstance(photo_id, str) or not photo_id.strip():
                raise ValueError("photo_id must be a nonempty string")
            if not isinstance(image_bytes, bytes):
                raise TypeError("photo bytes must be bytes")
            assessment = predict_cleanliness(
                self._model_bundle,
                BytesIO(image_bytes),
                photo_id=photo_id,
            )
            if assessment.cleanliness_state == "dirty":
                findings.append(
                    AIFinding(
                        detection_id=f"{photo_id}:cleanliness",
                        source_photo_id=photo_id,
                        category=ConditionCategory.CLEANLINESS,
                        severity=Severity.MINOR,
                        confidence=assessment.confidence,
                    )
                )
        return findings


class NoDetectionsAnalyzer(AIAnalyzer):
    """Safe MVP stub that produces no AI findings."""

    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        return []
