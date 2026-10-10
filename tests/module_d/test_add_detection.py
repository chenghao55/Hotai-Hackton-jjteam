"""Adding findings to an existing Case, and appeals returning the Case to UNASSIGNED."""

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.cases as api
from backend.state.cases import cases
from module_d import (
    Case, CaseStatus as T, ConditionCategory as C, DetectionInput, ReviewState as R, Severity as S,
    add_detection, appeal_detection, create_case, demo_policy,
)


def finding_input(detection_id="d2", **changes):
    values = dict(detection_id=detection_id, borrow_photo_id="b2", return_photo_id="r2",
                  category=C.CLEANLINESS, severity=S.MODERATE, confidence=0.55)
    return DetectionInput(**(values | changes))


def one_finding_case(status=T.UNASSIGNED):
    case = create_case("c1", [finding_input("d1", category=C.SCRATCH, severity=S.MINOR, confidence=0.9)],
                       policy=demo_policy())
    case.status = status
    return case


def test_add_detection_appends_assesses_and_recalculates_priority():
    case = one_finding_case()
    assert case.priority_score == 20
    added = add_detection(case, finding_input(), policy=demo_policy())
    assert [d.detection_id for d in case.detections] == ["d1", "d2"]
    assert added is case.detections[1]
    assert added.review_state == R.NEEDS_REVIEW          # 0.55 < 0.70
    assert case.priority_score == 35                     # max(scratch/minor 20, cleanliness/moderate 35)
    assert case.status == T.UNASSIGNED


def test_add_detection_uses_confidence_threshold():
    case = one_finding_case()
    added = add_detection(case, finding_input(confidence=0.8), policy=demo_policy())
    assert added.review_state == R.AUTO_ACCEPTED


@pytest.mark.parametrize("status", [T.DISPATCHED, T.PROCESSING, T.PENDING_PAYMENT, T.COMPLETED])
def test_add_detection_requires_unassigned_and_is_atomic(status):
    case = one_finding_case(status)
    before = deepcopy(case)
    with pytest.raises(ValueError, match="add_detection requires unassigned"):
        add_detection(case, finding_input(), policy=demo_policy())
    assert case == before


@pytest.mark.parametrize("bad", [dict(detection_id="d1"), dict(confidence=1.5), dict(return_photo_id="")])
def test_invalid_added_detection_is_atomic(bad):
    case = one_finding_case()
    before = deepcopy(case)
    with pytest.raises(ValueError):
        add_detection(case, finding_input(**bad), policy=demo_policy())
    assert case == before


@pytest.mark.parametrize("status", list(T))
def test_appeal_returns_case_to_unassigned_and_keeps_payment(status):
    case = one_finding_case()
    case.status = status
    case.payment_amount = 0 if status == T.UNASSIGNED else 1800
    appeal_detection(case, "d1", policy=demo_policy())
    assert case.status == T.UNASSIGNED
    assert case.payment_amount == (0 if status == T.UNASSIGNED else 1800)
    assert case.detections[0].review_state == R.NEEDS_REVIEW


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    cases.clear()
    with TestClient(app) as client:
        yield client
    cases.clear()


def body(**changes):
    values = {"detection_id": "d2", "borrow_photo_id": "b2", "return_photo_id": "r2",
              "category": "cleanliness", "severity": "moderate", "confidence": 0.55}
    return values | changes


def test_add_detection_route(client):
    cases["c1"] = one_finding_case()
    response = client.post("/cases/c1/detections", json=body())
    assert response.status_code == 200
    data = response.json()
    assert [d["detection_id"] for d in data["detections"]] == ["d1", "d2"]
    assert data["detections"][1]["review_state"] == "needs_review"
    assert data["priority_score"] == 35
    assert len(client.get("/cases").json()) == 1          # same vehicle stays one Case


def test_add_detection_route_unknown_case_is_404(client):
    assert client.post("/cases/missing/detections", json=body()).status_code == 404


@pytest.mark.parametrize("payload,status", [
    (body(detection_id="d1"), 409),                        # duplicate detection_id
    (body(confidence=1.5), 422),                           # invalid value
    (body(category="dent"), 422),                          # unknown category
    (body(extra="x"), 422),                                # extra fields are forbidden
])
def test_add_detection_route_errors_leave_case_unchanged(client, payload, status):
    cases["c1"] = one_finding_case()
    before = deepcopy(cases["c1"])
    assert client.post("/cases/c1/detections", json=payload).status_code == status
    assert cases["c1"] == before


def test_add_detection_route_rejects_dispatched_case(client):
    cases["c1"] = one_finding_case(T.DISPATCHED)
    response = client.post("/cases/c1/detections", json=body())
    assert response.status_code == 409
    assert len(cases["c1"].detections) == 1


def test_appeal_route_returns_completed_case_to_unassigned(client):
    case = one_finding_case(T.COMPLETED)
    case.payment_amount = 3500
    cases["c1"] = case
    response = client.post("/cases/c1/detections/d1/appeal")
    assert response.status_code == 200
    assert response.json()["status"] == "unassigned"
    assert response.json()["payment_amount"] == 3500
