"""Temporary process-local Case storage for the MVP backend."""

from module_d import logic
from module_d.models import Case, ConditionCategory, Detection, ReviewState, Severity
from module_d.policy import demo_policy


_demo_case = Case(
    "demo-001",
    [
        Detection(
            detection_id="demo-detection-001",
            borrow_photo_id="demo-borrow-001",
            return_photo_id="demo-return-001",
            category=ConditionCategory.SCRATCH,
            severity=Severity.MINOR,
            confidence=0.5,
            review_state=ReviewState.NEEDS_REVIEW,
        )
    ],
)
_demo_policy = demo_policy()
logic.assess_detection(_demo_case.detections[0], _demo_policy)
logic.calculate_priority(_demo_case, _demo_policy)

cases: dict[str, Case] = {_demo_case.case_id: _demo_case}
