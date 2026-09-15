from dataclasses import replace

import pytest

from module_d import Case, CaseStatus, ConditionCategory as C, Detection, ReviewState as R, Severity as S


def detection(**changes):
    values = dict(detection_id="d1", borrow_photo_id="b1", return_photo_id="r1", category=C.SCRATCH,
                  severity=S.MINOR, confidence=0.7, review_state=R.AUTO_ACCEPTED)
    return Detection(**(values | changes))


def test_enum_values():
    assert [v.value for v in C] == ["scratch", "collision_damage", "cleanliness"]
    assert [v.value for v in S] == ["minor", "moderate", "severe"]
    assert [v.value for v in R] == ["needs_review", "auto_accepted", "confirmed", "rejected", "corrected"]
    assert [v.value for v in CaseStatus] == ["unassigned", "dispatched", "processing", "pending_payment", "completed"]


@pytest.mark.parametrize("confidence", [0, 0.1, 0.4, 0.7, 1])
def test_confidence_accepts_full_domain_without_b_threshold(confidence):
    assert detection(confidence=confidence).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan"), float("inf"), -float("inf"), True, "0.7", None])
def test_invalid_confidence(confidence):
    with pytest.raises(ValueError):
        detection(confidence=confidence)


@pytest.mark.parametrize("changes", [
    {"detection_id": " "}, {"category": "scratch"},
    {"severity": None}, {"review_state": "confirmed"}, {"review_note": 4},
])
def test_invalid_detection_fields(changes):
    with pytest.raises(ValueError):
        detection(**changes)


@pytest.mark.parametrize("field", ["borrow_photo_id", "return_photo_id"])
@pytest.mark.parametrize("value", ["", "   ", None, 123, True])
def test_invalid_photo_references(field, value):
    with pytest.raises(ValueError, match=field):
        detection(**{field: value})


@pytest.mark.parametrize("field", ["borrow_photo_id", "return_photo_id"])
def test_photo_references_are_required(field):
    values = vars(detection()).copy()
    del values[field]
    with pytest.raises(TypeError, match=field):
        Detection(**values)


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
    assert first.priority_score is None and first.payment_amount == 0
    first.detections.append(detection())
    assert second.detections == []


def test_case_ids_unique_but_same_photo_allowed():
    assert len(Case("c", [detection(), detection(detection_id="d2")]).detections) == 2
    with pytest.raises(ValueError):
        Case("c", [detection(), detection(borrow_photo_id="b2", return_photo_id="r2")])


@pytest.mark.parametrize("amount", [-1, 1.5, True, "100", None])
def test_invalid_payment(amount):
    with pytest.raises(ValueError):
        Case("c", payment_amount=amount)


@pytest.mark.parametrize("changes", [{"case_id": ""}, {"detections": ()}, {"detections": [None]}, {"priority_score": "50"}, {"status": "completed"}])
def test_invalid_case_fields(changes):
    with pytest.raises(ValueError):
        Case(**({"case_id": "c"} | changes))


def test_models_do_not_infer_workflow_priority_or_payment():
    case = Case(
        "c",
        [detection(review_state=R.NEEDS_REVIEW)],
        priority_score=30,
        status=CaseStatus.PROCESSING,
        payment_amount=500,
    )
    assert case.status == CaseStatus.PROCESSING
    assert case.priority_score == 30 and case.payment_amount == 500


def test_explicit_validation_rechecks_nested_mutations():
    case = Case("c", [detection()])
    case.detections[0].confidence = -1
    with pytest.raises(ValueError):
        case.validate()


@pytest.mark.parametrize(
    "score",
    [-1, 101, 1.5, 50.0, True, False, "50"],
)
def test_invalid_priority_score(score):
    with pytest.raises(ValueError):
        Case("c", priority_score=score)


@pytest.mark.parametrize("score", [None, 0, 1, 50, 99, 100])
def test_valid_priority_score(score):
    assert Case("c", priority_score=score).priority_score == score


def test_zero_score_is_distinct_from_uncalculated():
    assert Case("uncalculated").priority_score is None
    calculated = Case("calculated", priority_score=0)
    assert calculated.priority_score is not None
    assert type(calculated.priority_score) is int
    assert calculated.priority_score == 0


def test_score_validation_rechecks_mutations():
    case = Case("c", priority_score=0)
    case.priority_score = False
    with pytest.raises(ValueError, match="priority_score"):
        case.validate()
