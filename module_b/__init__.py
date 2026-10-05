"""Single-image vehicle-condition models for Module B."""

from .analyzer import (
    AIFinding,
    AIAnalyzer,
    CleanlinessModelAnalyzer,
    DamageModelAnalyzer,
    NoDetectionsAnalyzer,
)
from .inference import ModelBundle, load_claim_model, predict_claim
from .interface import ModuleB
from .orchestrator import CaseBuildingModuleB
from .schemas import (
    CleanlinessEvidence,
    PhotoClaimResult,
    PhotoCleanlinessAssessment,
    PhotoConditionResult,
    PhotoDamageAssessment,
)

__all__ = [
    "AIFinding",
    "AIAnalyzer",
    "CaseBuildingModuleB",
    "CleanlinessEvidence",
    "CleanlinessModelBundle",
    "CleanlinessModelAnalyzer",
    "DamageSegmentationBundle",
    "DamageModelAnalyzer",
    "ModelBundle",
    "ModuleB",
    "NoDetectionsAnalyzer",
    "PhotoClaimResult",
    "PhotoCleanlinessAssessment",
    "PhotoConditionResult",
    "PhotoDamageAssessment",
    "load_claim_model",
    "load_cleanliness_model",
    "load_damage_segmentation_model",
    "predict_claim",
    "predict_cleanliness",
    "predict_damage_assessment",
    "predict_damage_conditions",
]


def __getattr__(name: str):
    if name in {
        "CleanlinessModelBundle",
        "load_cleanliness_model",
        "predict_cleanliness",
    }:
        from . import cleanliness_inference

        return getattr(cleanliness_inference, name)
    if name in {
        "DamageSegmentationBundle",
        "load_damage_segmentation_model",
        "predict_damage_assessment",
        "predict_damage_conditions",
    }:
        from . import damage_inference

        return getattr(damage_inference, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
