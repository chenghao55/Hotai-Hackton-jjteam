"""Configurable review and priority inputs, without decision operations."""

from dataclasses import dataclass

from .models import ConditionCategory, Priority, Severity, _enum, _probability


@dataclass
class DecisionPolicy:
    priority_by_condition: dict[tuple[ConditionCategory, Severity], Priority]
    review_confidence_threshold: float = 0.70

    def __post_init__(self) -> None:
        self.validate()
        self.priority_by_condition = dict(self.priority_by_condition)

    def validate(self) -> None:
        _probability(self.review_confidence_threshold, "review_confidence_threshold")
        if not isinstance(self.priority_by_condition, dict):
            raise ValueError("priority_by_condition must be a dictionary")
        for key, priority in self.priority_by_condition.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError("Policy keys must be (category, severity) tuples")
            _enum(key[0], ConditionCategory, "policy category")
            _enum(key[1], Severity, "policy severity")
            _enum(priority, Priority, "policy priority")
        expected = {(category, severity) for category in ConditionCategory for severity in Severity}
        if set(self.priority_by_condition) != expected:
            raise ValueError("Policy must cover every category/severity combination")


def demo_policy() -> DecisionPolicy:
    """Example values only: these are not validated Hotai business rules."""
    return DecisionPolicy(priority_by_condition={
        (ConditionCategory.SCRATCH, Severity.MINOR): Priority.LOW,
        (ConditionCategory.SCRATCH, Severity.MODERATE): Priority.MEDIUM,
        (ConditionCategory.SCRATCH, Severity.SEVERE): Priority.HIGH,
        (ConditionCategory.COLLISION_DAMAGE, Severity.MINOR): Priority.MEDIUM,
        (ConditionCategory.COLLISION_DAMAGE, Severity.MODERATE): Priority.HIGH,
        (ConditionCategory.COLLISION_DAMAGE, Severity.SEVERE): Priority.HIGH,
        (ConditionCategory.CLEANLINESS, Severity.MINOR): Priority.LOW,
        (ConditionCategory.CLEANLINESS, Severity.MODERATE): Priority.MEDIUM,
        (ConditionCategory.CLEANLINESS, Severity.SEVERE): Priority.HIGH,
    })
