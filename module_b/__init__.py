"""Single-image vehicle-condition models for Module B."""

from .damage_inference import (
    DamageSegmentationBundle,
    load_damage_segmentation_model,
    predict_damage_assessment,
    predict_damage_conditions,
)
from .inference import ModelBundle, load_claim_model, predict_claim
from .schemas import PhotoClaimResult, PhotoConditionResult, PhotoDamageAssessment

__all__ = [
    "DamageSegmentationBundle",
    "ModelBundle",
    "PhotoClaimResult",
    "PhotoConditionResult",
    "PhotoDamageAssessment",
    "load_claim_model",
    "load_damage_segmentation_model",
    "predict_claim",
    "predict_damage_assessment",
    "predict_damage_conditions",
]
