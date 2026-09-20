"""Replaceable AI-analysis contracts for Module B orchestration."""


from abc import ABC, abstractmethod
from dataclasses import dataclass

from module_d.models import ConditionCategory, Severity


@dataclass(frozen=True)
class AIFinding:
    """One vehicle-condition finding produced by an AI analyzer."""

    detection_id: str
    category: ConditionCategory
    severity: Severity
    confidence: float

# TODO: implement implement ai analyzer 鄭宇勳 class AIAnalyzer(ABC):
    """Dependency implemented later by the real AI or computer-vision model."""

    @abstractmethod
    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        raise NotImplementedError


class NoDetectionsAnalyzer(AIAnalyzer):
    """Safe MVP stub that produces no AI findings."""

    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        return []
