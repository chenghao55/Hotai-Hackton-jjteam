"""Configurable review and priority inputs, without decision operations."""

from dataclasses import dataclass

from .models import ConditionCategory, Severity, _enum, _probability


@dataclass
class DecisionPolicy:
    priority_score_by_condition: dict[tuple[ConditionCategory, Severity], int]
    review_confidence_threshold: float = 0.70

    def __post_init__(self) -> None:
        self.validate()
        self.priority_score_by_condition = dict(self.priority_score_by_condition)

    def validate(self) -> None:
        _probability(self.review_confidence_threshold, "review_confidence_threshold")
        if not isinstance(self.priority_score_by_condition, dict):
            raise ValueError("priority_score_by_condition must be a dictionary")
        for key, score in self.priority_score_by_condition.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError("Policy keys must be (category, severity) tuples")

            _enum(key[0], ConditionCategory, "policy category")
            _enum(key[1], Severity, "policy severity")

            if type(score) is not int or not 0 <= score <= 100:
                raise ValueError("priority score must be an integer within [0, 100]")
        expected = {(category, severity) for category in ConditionCategory for severity in Severity}
        if set(self.priority_score_by_condition) != expected:
            raise ValueError("Policy must cover every category/severity combination")


def demo_policy() -> DecisionPolicy:
    """Prototype scores only: not validated Hotai/iRent business rules."""
    return DecisionPolicy(priority_score_by_condition={
        (ConditionCategory.SCRATCH, Severity.MINOR): 20,
        (ConditionCategory.SCRATCH, Severity.MODERATE): 45,
        (ConditionCategory.SCRATCH, Severity.SEVERE): 70,

        (ConditionCategory.COLLISION_DAMAGE, Severity.MINOR): 50,
        (ConditionCategory.COLLISION_DAMAGE, Severity.MODERATE): 75,
        (ConditionCategory.COLLISION_DAMAGE, Severity.SEVERE): 95,

        (ConditionCategory.CLEANLINESS, Severity.MINOR): 10,
        (ConditionCategory.CLEANLINESS, Severity.MODERATE): 35,
        (ConditionCategory.CLEANLINESS, Severity.SEVERE): 60,
    })
