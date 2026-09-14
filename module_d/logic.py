"""Deterministic, in-place domain operations for Module D."""

from dataclasses import replace

from .models import Case, CaseStatus, ConditionCategory, Detection, ReviewState, Severity
from .policy import DecisionPolicy

# 在那些狀態下 可以計算Case priority
_ACTIONABLE = frozenset({ReviewState.AUTO_ACCEPTED, ReviewState.CONFIRMED, ReviewState.CORRECTED})


def assess_detection(detection: Detection, policy: DecisionPolicy) -> None:
    """判斷該detection是否需要被review. 填入`detection.review_state`; never overwrite a human decision."""
    detection.validate()
    policy.validate()
    if detection.review_state not in {ReviewState.NEEDS_REVIEW, ReviewState.AUTO_ACCEPTED}:
        raise ValueError("Initial assessment cannot overwrite a human review")
    detection.review_state = (
        ReviewState.NEEDS_REVIEW
        if detection.confidence < policy.review_confidence_threshold
        else ReviewState.AUTO_ACCEPTED
    )
    detection.validate()


def calculate_priority(case: Case, policy: DecisionPolicy) -> None:
    """Store the highest contributing numeric score, preserving zero."""
    case.validate()
    policy.validate()
    scores = []
    for detection in case.detections:
        if detection.review_state not in _ACTIONABLE:
            continue
        if detection.review_state == ReviewState.CORRECTED:
            key = (detection.reviewed_category, detection.reviewed_severity)
        else:
            key = (detection.category, detection.severity)
        scores.append(policy.priority_score_by_condition[key])
    case.priority_score = max(scores, default=None)
    case.validate()


def needs_review(case: Case) -> bool:
    """Does this case need review. 只要有detection需要人工驗證就return True"""
    case.validate()
    return any(d.review_state == ReviewState.NEEDS_REVIEW for d in case.detections)


def apply_review(
    case: Case,
    detection_id: str,
    result: ReviewState,
    *,
    policy: DecisionPolicy,
    reviewed_category: ConditionCategory | None = None,
    reviewed_severity: Severity | None = None,
    review_note: str | None = None,
) -> None:
    """Replace the latest human review and recalculate the Case score in place."""
    case.validate()
    policy.validate()
    if not isinstance(result, ReviewState) or result not in {
        ReviewState.CONFIRMED, ReviewState.REJECTED, ReviewState.CORRECTED
    }:
        raise ValueError("Human result must be CONFIRMED, REJECTED, or CORRECTED")
    detection = next((d for d in case.detections if d.detection_id == detection_id), None)
    if detection is None:
        raise ValueError(f"Unknown detection_id: {detection_id!r}")
    if result != ReviewState.CORRECTED:
        reviewed_category = None
        reviewed_severity = None
    # Validate the proposed result and score before mutating the caller's objects.
    proposed = replace(
        detection, review_state=result, reviewed_category=reviewed_category,
        reviewed_severity=reviewed_severity, review_note=review_note,
    )
    proposed_case = replace(
        case, detections=[proposed if d is detection else d for d in case.detections]
    )
    calculate_priority(proposed_case, policy)
    detection.review_state = proposed.review_state
    detection.reviewed_category = proposed.reviewed_category
    detection.reviewed_severity = proposed.reviewed_severity
    detection.review_note = proposed.review_note
    detection.validate()
    case.priority_score = proposed_case.priority_score
    case.validate()


def set_payment_amount(case: Case, amount: int) -> None:
    """Update the assessed charge before billing or completion."""
    case.validate()
    if case.status not in {CaseStatus.UNASSIGNED, CaseStatus.DISPATCHED, CaseStatus.PROCESSING}:
        raise ValueError("Payment amount cannot change in PENDING_PAYMENT or COMPLETED")
    replace(case, payment_amount=amount)  # Constructor validates before mutation.
    case.payment_amount = amount
    case.validate()

# change status
def _require_status(case: Case, expected: CaseStatus, operation: str) -> None:
    case.validate()
    if case.status != expected:
        raise ValueError(f"{operation} requires {expected.value}; current status is {case.status.value}")


def dispatch_case(case: Case) -> None:
    _require_status(case, CaseStatus.UNASSIGNED, "dispatch_case")
    case.status = CaseStatus.DISPATCHED
    case.validate()


def start_processing(case: Case) -> None:
    _require_status(case, CaseStatus.DISPATCHED, "start_processing")
    case.status = CaseStatus.PROCESSING
    case.validate()


def finish_processing(case: Case) -> None:
    _require_status(case, CaseStatus.PROCESSING, "finish_processing")
    case.status = CaseStatus.PENDING_PAYMENT if case.payment_amount > 0 else CaseStatus.COMPLETED
    case.validate()


def complete_without_action(case: Case) -> None:
    """Close only resolved, non-actionable, zero-charge cases before processing."""
    case.validate()
    if case.status not in {CaseStatus.UNASSIGNED, CaseStatus.DISPATCHED}:
        raise ValueError("complete_without_action requires UNASSIGNED or DISPATCHED")
    if any(d.review_state in _ACTIONABLE for d in case.detections):
        raise ValueError("Cannot complete without action: actionable detections remain")
    if needs_review(case):
        raise ValueError("Cannot complete without action: detections need review")
    if case.payment_amount != 0:
        raise ValueError("Cannot complete without action: payment_amount must be zero")
    case.status = CaseStatus.COMPLETED
    case.validate()


def confirm_payment(case: Case) -> None:
    _require_status(case, CaseStatus.PENDING_PAYMENT, "confirm_payment")
    case.status = CaseStatus.COMPLETED
    case.validate()
