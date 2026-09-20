from copy import deepcopy
from dataclasses import replace

import pytest

from module_d import (
    Case, CaseStatus as T, ConditionCategory as C, Detection, DetectionInput, ReviewState as R,
    Severity as S, apply_review, assess_detection, calculate_priority, create_case,
    complete_without_action, confirm_payment, demo_policy, dispatch_case,
    finish_processing, needs_review, set_payment_amount, start_processing,
)


def finding(state=R.AUTO_ACCEPTED, **changes):
    values = dict(detection_id="d1", borrow_photo_id="b1", return_photo_id="r1", category=C.SCRATCH,
                  severity=S.MINOR, confidence=0.7, review_state=state)
    if state == R.CORRECTED:
        values.update(reviewed_category=C.COLLISION_DAMAGE, reviewed_severity=S.SEVERE)
    return Detection(**(values | changes))


def detection_input(**changes):
    values = dict(
        detection_id="d1",
        borrow_photo_id="borrow-1",
        return_photo_id="return-1",
        category=C.SCRATCH,
        severity=S.MINOR,
        confidence=0.7,
    )
    return DetectionInput(**(values | changes))


def test_create_case_without_detections():
    case = create_case("case-1", [], policy=demo_policy())

    assert case.case_id == "case-1"
    assert case.detections == []
    assert case.priority_score is None
    assert case.status == T.UNASSIGNED
    assert case.payment_amount == 0


def test_create_case_builds_and_assesses_one_detection():
    case = create_case("case-1", [detection_input()], policy=demo_policy())

    detection = case.detections[0]
    assert detection.detection_id == "d1"
    assert detection.borrow_photo_id == "borrow-1"
    assert detection.return_photo_id == "return-1"
    assert detection.category == C.SCRATCH
    assert detection.severity == S.MINOR
    assert detection.confidence == 0.7
    assert detection.review_state == R.AUTO_ACCEPTED
    assert case.priority_score == 20
    assert case.status == T.UNASSIGNED
    assert case.payment_amount == 0


def test_create_case_assesses_multiple_detections_and_uses_highest_priority():
    case = create_case("case-1", [
        detection_input(detection_id="scratch", confidence=0.69),
        detection_input(
            detection_id="collision",
            category=C.COLLISION_DAMAGE,
            severity=S.SEVERE,
            confidence=0.9,
        ),
    ], policy=demo_policy())

    assert [d.review_state for d in case.detections] == [R.NEEDS_REVIEW, R.AUTO_ACCEPTED]
    assert case.priority_score == 95


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), True])
def test_create_case_rejects_invalid_confidence_without_mutating_inputs(confidence):
    inputs = [detection_input(confidence=confidence)]
    original_input = inputs[0]

    with pytest.raises(ValueError, match="confidence"):
        create_case("case-1", inputs, policy=demo_policy())

    assert inputs == [original_input]
    assert inputs[0] is original_input


def test_create_case_rejects_duplicate_detection_ids_without_returning_a_case():
    inputs = [detection_input(), detection_input(return_photo_id="return-2")]

    with pytest.raises(ValueError, match="unique"):
        create_case("case-1", inputs, policy=demo_policy())

    assert inputs[0].detection_id == inputs[1].detection_id == "d1"


@pytest.mark.parametrize("confidence,state", [(0.1, R.NEEDS_REVIEW), (0.6999, R.NEEDS_REVIEW), (0.7, R.AUTO_ACCEPTED), (0.9, R.AUTO_ACCEPTED)])
def test_assessment_boundary_and_original_preservation(confidence, state):
    detection = finding(confidence=confidence, review_note="source note")
    before = deepcopy(detection)
    assert assess_detection(detection, demo_policy()) is None
    assert detection == replace(before, review_state=state)


def test_assessment_uses_custom_threshold():
    policy = demo_policy()
    policy.review_confidence_threshold = 0.8
    detection = finding(confidence=0.75)
    assess_detection(detection, policy)
    assert detection.review_state == R.NEEDS_REVIEW


@pytest.mark.parametrize("state", [R.CONFIRMED, R.REJECTED, R.CORRECTED])
def test_assessment_preserves_human_decision(state):
    detection = finding(state)
    before = deepcopy(detection)
    with pytest.raises(ValueError, match="human review"):
        assess_detection(detection, demo_policy())
    assert detection == before


@pytest.mark.parametrize("states", [[], [R.REJECTED], [R.NEEDS_REVIEW], [R.REJECTED, R.NEEDS_REVIEW]])
def test_no_contributors_clears_previous_score(states):
    case = Case("c", [finding(state, detection_id=str(i)) for i, state in enumerate(states)], priority_score=95)
    calculate_priority(case, demo_policy())
    assert case.priority_score is None


@pytest.mark.parametrize("state,score", [(R.AUTO_ACCEPTED, 20), (R.CONFIRMED, 20), (R.CORRECTED, 95)])
def test_priority_value_selection(state, score):
    case = Case("c", [finding(state)])
    calculate_priority(case, demo_policy())
    assert case.priority_score == score


def test_highest_score_wins_ignoring_pending_and_rejected():
    case = Case("c", [
        finding(detection_id="a"),
        finding(R.CONFIRMED, detection_id="b", severity=S.SEVERE),
        finding(R.REJECTED, detection_id="c", category=C.COLLISION_DAMAGE, severity=S.SEVERE),
        finding(R.NEEDS_REVIEW, detection_id="d", category=C.COLLISION_DAMAGE, severity=S.SEVERE),
    ])
    calculate_priority(case, demo_policy())
    assert case.priority_score == 70
    case.detections.reverse()
    calculate_priority(case, demo_policy())
    assert case.priority_score == 70


@pytest.mark.parametrize("confidence", [0, 0.1, 0.7, 1])
def test_priority_ignores_confidence(confidence):
    case = Case("c", [finding(confidence=confidence)])
    calculate_priority(case, demo_policy())
    assert case.priority_score == 20


def test_numeric_policy_and_zero_score():
    policy = demo_policy()
    policy.priority_score_by_condition[C.SCRATCH, S.MINOR] = 0
    case = Case("c", [finding()])
    calculate_priority(case, policy)
    assert case.priority_score == 0 and case.priority_score is not None
    policy.priority_score_by_condition[C.SCRATCH, S.MINOR] = 100
    calculate_priority(case, policy)
    assert case.priority_score == 100


@pytest.mark.parametrize("states,expected", [([], False), ([R.NEEDS_REVIEW], True), ([R.CONFIRMED, R.AUTO_ACCEPTED, R.REJECTED, R.CORRECTED], False), ([R.CONFIRMED, R.NEEDS_REVIEW], True)])
def test_needs_review_is_read_only(states, expected):
    case = Case("c", [finding(state, detection_id=str(i)) for i, state in enumerate(states)])
    before = deepcopy(case)
    assert needs_review(case) is expected
    assert case == before


@pytest.mark.parametrize("result,score", [(R.CONFIRMED, 20), (R.REJECTED, None), (R.CORRECTED, 95)])
def test_human_review_updates_score_preserves_originals_and_identity(result, score):
    detection = finding(R.NEEDS_REVIEW)
    case = Case("c", [detection], status=T.DISPATCHED, payment_amount=300)
    original = deepcopy(detection)
    apply_review(case, "d1", result, policy=demo_policy(),
                 reviewed_category=C.COLLISION_DAMAGE, reviewed_severity=S.SEVERE,
                 review_note="staff result")
    assert case.detections[0] is detection
    assert detection.review_state == result
    assert detection.review_note == "staff result"
    assert (detection.category, detection.severity, detection.confidence,
            detection.borrow_photo_id, detection.return_photo_id) == (
        original.category, original.severity, original.confidence,
        original.borrow_photo_id, original.return_photo_id)
    assert case.priority_score == score
    assert case.status == T.DISPATCHED and case.payment_amount == 300
    if result != R.CORRECTED:
        assert detection.reviewed_category is None and detection.reviewed_severity is None


@pytest.mark.parametrize("result", [R.CONFIRMED, R.REJECTED, R.CORRECTED])
def test_rereview_replaces_previous_values(result):
    case = Case("c", [finding(R.CORRECTED, review_note="old")])
    kwargs = dict(reviewed_category=C.CLEANLINESS, reviewed_severity=S.MODERATE) if result == R.CORRECTED else {}
    apply_review(case, "d1", result, policy=demo_policy(), **kwargs)
    detection = case.detections[0]
    assert detection.review_note is None
    assert detection.review_state == result
    assert case.priority_score == {R.CONFIRMED: 20, R.REJECTED: None, R.CORRECTED: 35}[result]
    assert detection.reviewed_category == (C.CLEANLINESS if result == R.CORRECTED else None)
    assert detection.reviewed_severity == (S.MODERATE if result == R.CORRECTED else None)


@pytest.mark.parametrize("state", list(R))
def test_staff_can_revise_every_existing_state(state):
    case = Case("c", [finding(state)])
    apply_review(case, "d1", R.CONFIRMED, policy=demo_policy())
    assert case.detections[0].review_state == R.CONFIRMED


@pytest.mark.parametrize("kwargs", [
    {"detection_id": "missing"}, {"result": R.NEEDS_REVIEW}, {"result": R.AUTO_ACCEPTED},
    {"result": "confirmed"}, {"result": R.CORRECTED},
    {"result": R.CORRECTED, "reviewed_category": C.CLEANLINESS},
    {"result": R.CORRECTED, "reviewed_severity": S.SEVERE},
    {"result": R.CORRECTED, "reviewed_category": C.SCRATCH, "reviewed_severity": S.MINOR},
    {"review_note": 10},
])
def test_invalid_review_is_atomic(kwargs):
    case = Case("c", [finding()], priority_score=20)
    before = deepcopy(case)
    arguments = dict(detection_id="d1", result=R.CONFIRMED, policy=demo_policy()) | kwargs
    with pytest.raises(ValueError):
        apply_review(case, **arguments)
    assert case == before


def test_rejecting_highest_finding_recalculates_from_remaining():
    case = Case("c", [finding(detection_id="small"), finding(R.CORRECTED)], priority_score=95)
    apply_review(case, "d1", R.REJECTED, policy=demo_policy())
    assert case.priority_score == 20


@pytest.mark.parametrize("status", [T.UNASSIGNED, T.DISPATCHED, T.PROCESSING])
@pytest.mark.parametrize("amount", [0, 1, 500])
def test_payment_updates_only_amount(status, amount):
    case = Case("c", [finding()], priority_score=95, status=status, payment_amount=100)
    before = deepcopy(case)
    set_payment_amount(case, amount)
    assert case == replace(before, payment_amount=amount)


@pytest.mark.parametrize("amount", [-1, True, False, 50.0, "50", None])
def test_invalid_payment_is_atomic(amount):
    case = Case("c", payment_amount=100)
    before = deepcopy(case)
    with pytest.raises(ValueError):
        set_payment_amount(case, amount)
    assert case == before


@pytest.mark.parametrize("status", [T.PENDING_PAYMENT, T.COMPLETED])
def test_payment_locked(status):
    case = Case("c", status=status, payment_amount=100)
    before = deepcopy(case)
    with pytest.raises(ValueError, match="cannot change"):
        set_payment_amount(case, 0)
    assert case == before


@pytest.mark.parametrize("operation,source,target,amount", [
    (dispatch_case, T.UNASSIGNED, T.DISPATCHED, 0),
    (start_processing, T.DISPATCHED, T.PROCESSING, 500),
    (confirm_payment, T.PENDING_PAYMENT, T.COMPLETED, 500),
])
def test_workflow_preserves_fields_and_does_not_gate_pending_review(operation, source, target, amount):
    case = Case("c", [finding(R.NEEDS_REVIEW)], priority_score=0, status=source, payment_amount=amount)
    before = deepcopy(case)
    detection = case.detections[0]
    operation(case)
    assert case == replace(before, status=target)
    assert case.detections[0] is detection


@pytest.mark.parametrize("amount", [0, 500])
def test_finish_processing_with_pending_review_is_atomic(amount):
    case = Case(
        "c",
        [finding(R.NEEDS_REVIEW)],
        priority_score=0,
        status=T.PROCESSING,
        payment_amount=amount,
    )
    before = deepcopy(case)

    with pytest.raises(ValueError, match="need review"):
        finish_processing(case)

    assert case == before


@pytest.mark.parametrize("operation,source", [
    (dispatch_case, T.UNASSIGNED), (start_processing, T.DISPATCHED),
    (finish_processing, T.PROCESSING), (confirm_payment, T.PENDING_PAYMENT),
])
def test_all_illegal_workflow_sources_are_atomic(operation, source):
    for status in T:
        if status == source:
            continue
        case = Case("c", status=status, payment_amount=300)
        before = deepcopy(case)
        with pytest.raises(ValueError, match="requires"):
            operation(case)
        assert case == before


@pytest.mark.parametrize("status", [T.UNASSIGNED, T.DISPATCHED])
@pytest.mark.parametrize("rejected", [False, True])
def test_no_action_completion_preserves_history(status, rejected):
    detections = [finding(R.REJECTED), finding(R.REJECTED, detection_id="d2")] if rejected else []
    case = Case("c", detections, status=status)
    before = deepcopy(case)
    complete_without_action(case)
    assert case == replace(before, status=T.COMPLETED)


@pytest.mark.parametrize("state", [R.NEEDS_REVIEW, R.AUTO_ACCEPTED, R.CONFIRMED, R.CORRECTED])
@pytest.mark.parametrize("score", [None, 0])
def test_no_action_checks_detections_not_cached_score(state, score):
    case = Case("c", [finding(state)], priority_score=score)
    before = deepcopy(case)
    with pytest.raises(ValueError):
        complete_without_action(case)
    assert case == before


@pytest.mark.parametrize("status", [T.PROCESSING, T.PENDING_PAYMENT, T.COMPLETED])
def test_no_action_illegal_status(status):
    case = Case("c", status=status)
    with pytest.raises(ValueError, match="requires"):
        complete_without_action(case)
    assert case.status == status


def test_no_action_positive_charge_rejected():
    case = Case("c", payment_amount=1)
    with pytest.raises(ValueError, match="payment_amount"):
        complete_without_action(case)
    assert case.status == T.UNASSIGNED


@pytest.mark.parametrize("status", list(T))
def test_priority_recalculation_never_advances_status(status):
    case = Case("c", [finding()], status=status, payment_amount=400)
    before = deepcopy(case)
    calculate_priority(case, demo_policy())
    assert case == replace(before, priority_score=20)


@pytest.mark.parametrize("operation", [
    lambda case, policy: calculate_priority(case, policy),
    lambda case, policy: apply_review(case, "d1", R.REJECTED, policy=policy),
    lambda case, policy: assess_detection(case.detections[0], policy),
])
def test_invalid_mutated_policy_leaves_case_unchanged(operation):
    case = Case("c", [finding()], priority_score=20)
    policy = demo_policy()
    policy.priority_score_by_condition[C.SCRATCH, S.MINOR] = True
    before = deepcopy(case)
    with pytest.raises(ValueError):
        operation(case, policy)
    assert case == before


def test_workflow_validates_mutated_case_before_changing_status():
    case = Case("c")
    case.payment_amount = True
    with pytest.raises(ValueError):
        dispatch_case(case)
    assert case.status == T.UNASSIGNED
