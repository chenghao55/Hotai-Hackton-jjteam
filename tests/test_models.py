from dataclasses import replace

import pytest

from module_d import Case, CaseStatus, ConditionCategory as C, Detection, Priority, ReviewState as R, Severity as S


def detection(**changes):
    values = dict(detection_id="d1", photo_id="p1", category=C.SCRATCH,
                  severity=S.MINOR, confidence=0.7, review_state=R.AUTO_ACCEPTED)
    return Detection(**(values | changes))


def test_enum_values():
    assert [v.value for v in C] == ["scratch", "collision_damage", "cleanliness"]
    assert [v.value for v in S] == ["minor", "moderate", "severe"]
    assert [v.value for v in R] == ["needs_review", "auto_accepted", "confirmed", "rejected", "corrected"]
    assert [v.value for v in Priority] == ["low", "medium", "high"]
    assert [v.value for v in CaseStatus] == ["unassigned", "dispatched", "processing", "pending_payment", "completed"]


@pytest.mark.parametrize("confidence", [0, 0.1, 0.4, 0.7, 1])
def test_confidence_accepts_full_domain_without_b_threshold(confidence):
    assert detection(confidence=confidence).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan"), float("inf"), -float("inf"), True, "0.7", None])
def test_invalid_confidence(confidence):
    with pytest.raises(ValueError):
        detection(confidence=confidence)


@pytest.mark.parametrize("changes", [
    {"detection_id": " "}, {"photo_id": ""}, {"category": "scratch"},
    {"severity": None}, {"review_state": "confirmed"}, {"review_note": 4},
])
def test_invalid_detection_fields(changes):
    with pytest.raises(ValueError):
        detection(**changes)


@pytest.mark.parametrize("category,severity", [(C.SCRATCH, S.SEVERE), (C.CLEANLINESS, S.MINOR), (C.COLLISION_DAMAGE, S.MODERATE)])
def test_correction_preserves_originals(category, severity):
    original = detection()
    corrected = replace(original, review_state=R.CORRECTED,
                        reviewed_category=category, reviewed_severity=severity)
    assert (corrected.category, corrected.severity, corrected.confidence) == (C.SCRATCH, S.MINOR, 0.7)
    assert (corrected.reviewed_category, corrected.reviewed_severity) == (category, severity)
    assert original.review_state == R.AUTO_ACCEPTED


@pytest.mark.parametrize("changes", [
    {}, {"reviewed_category": C.CLEANLINESS}, {"reviewed_severity": S.SEVERE},
    {"reviewed_category": C.SCRATCH, "reviewed_severity": S.MINOR},
    {"reviewed_category": "cleanliness", "reviewed_severity": S.SEVERE},
])
def test_invalid_corrections(changes):
    with pytest.raises(ValueError):
        detection(review_state=R.CORRECTED, **changes)


@pytest.mark.parametrize("state", [R.NEEDS_REVIEW, R.AUTO_ACCEPTED, R.CONFIRMED, R.REJECTED])
def test_noncorrected_states_have_no_reviewed_values(state):
    assert detection(review_state=state).reviewed_category is None
    with pytest.raises(ValueError):
        detection(review_state=state, reviewed_category=C.CLEANLINESS)
    with pytest.raises(ValueError):
        detection(review_state=state, reviewed_severity=S.SEVERE)


def test_case_defaults_and_independent_lists():
    first, second = Case("c1"), Case("c2")
    assert first.status == CaseStatus.UNASSIGNED
    assert first.priority is None and first.payment_amount == 0
    first.detections.append(detection())
    assert second.detections == []


def test_case_ids_unique_but_same_photo_allowed():
    assert len(Case("c", [detection(), detection(detection_id="d2")]).detections) == 2
    with pytest.raises(ValueError):
        Case("c", [detection(), detection(photo_id="p2")])


@pytest.mark.parametrize("amount", [-1, 1.5, True, "100", None])
def test_invalid_payment(amount):
    with pytest.raises(ValueError):
        Case("c", payment_amount=amount)


@pytest.mark.parametrize("changes", [{"case_id": ""}, {"detections": ()}, {"detections": [None]}, {"priority": "high"}, {"status": "completed"}])
def test_invalid_case_fields(changes):
    with pytest.raises(ValueError):
        Case(**({"case_id": "c"} | changes))


def test_models_do_not_infer_workflow_priority_or_payment():
    case = Case("c", [detection(review_state=R.NEEDS_REVIEW)],
                priority=Priority.LOW, status=CaseStatus.PROCESSING, payment_amount=500)
    assert case.status == CaseStatus.PROCESSING
    assert case.priority == Priority.LOW and case.payment_amount == 500


def test_explicit_validation_rechecks_nested_mutations():
    case = Case("c", [detection()])
    case.detections[0].confidence = -1
    with pytest.raises(ValueError):
        case.validate()
