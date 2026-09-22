"""Single-image vehicle-condition models for Module B."""

from .analyzer import AIFinding, AIAnalyzer, DamageModelAnalyzer, NoDetectionsAnalyzer
from .damage_inference import (
    DamageSegmentationBundle,
    load_damage_segmentation_model,
    predict_damage_assessment,
    predict_damage_conditions,
)
from .inference import ModelBundle, load_claim_model, predict_claim
from .interface import ModuleB
from .orchestrator import CaseBuildingModuleB
from .schemas import PhotoClaimResult, PhotoConditionResult, PhotoDamageAssessment

__all__ = [
    "AIFinding",
    "AIAnalyzer",
    "CaseBuildingModuleB",
    "DamageSegmentationBundle",
    "DamageModelAnalyzer",
    "ModelBundle",
    "ModuleB",
    "NoDetectionsAnalyzer",
    "PhotoClaimResult",
    "PhotoConditionResult",
    "PhotoDamageAssessment",
    "load_claim_model",
    "load_damage_segmentation_model",
    "predict_claim",
    "predict_damage_assessment",
    "predict_damage_conditions",
]
