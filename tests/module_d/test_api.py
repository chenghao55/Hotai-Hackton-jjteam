from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from module_d import api, logic
from module_d.models import Case, CaseStatus, ConditionCategory, Detection, ReviewState, Severity


@pytest.fixture
def client(monkeypatch):
    # Each test owns its store; never mutate the manual-testing demo data.
    monkeypatch.setattr(api, "cases", {})
    with TestClient(api.app) as client:
        yield client


def test_empty_list(client):
    response = client.get("/cases")
    assert response.status_code == 200
    assert response.json() == []


def create_payload(**changes):
    payload = {
        "case_id": "new-case",
        "detections": [{
            "detection_id": "new-detection",
            "borrow_photo_id": "borrow-1",
            "return_photo_id": "return-1",
            "category": "scratch",
            "severity": "minor",
            "confidence": 0.5,
        }],
    }
    return payload | changes


def pending_detection(detection_id="d1", **changes):
    values = {
        "detection_id": detection_id,
        "borrow_photo_id": "borrow-1",
        "return_photo_id": "return-1",
        "category": ConditionCategory.SCRATCH,
        "severity": Severity.MINOR,
        "confidence": 0.5,
        "review_state": ReviewState.NEEDS_REVIEW,
    }
    return Detection(**(values | changes))


@pytest.mark.parametrize("score", [None, 0, 100])
def test_case_serialization(client, score):
    case = Case("c1", [Detection(
        "d1", "borrow1", "return1", ConditionCategory.SCRATCH,
        Severity.MINOR, 0.65, ReviewState.NEEDS_REVIEW,
    )], priority_score=score, payment_amount=123)
    api.cases[case.case_id] = case
    before = deepcopy(case)
    response = client.get("/cases")
    assert response.status_code == 200
    assert response.json() == [{
        "case_id": "c1", "status": "unassigned", "priority_score": score,
        "payment_amount": 123, "detections": [{
            "detection_id": "d1", "borrow_photo_id": "borrow1", "return_photo_id": "return1",
            "category": "scratch", "severity": "minor", "confidence": 0.65,
            "review_state": "needs_review", "source_photo_id": None, "reviewed_category": None,
            "reviewed_severity": None, "review_note": None,
        }],
    }]
    assert case == before


def test_get_existing_and_missing_case(client):
    api.cases["c1"] = Case("c1")
    assert client.get("/cases/c1").json()["case_id"] == "c1"
    response = client.get("/cases/missing")
    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_create_case_assesses_and_scores_detections(client):
    response = client.post("/cases", json=create_payload())
    assert response.status_code == 201
    assert response.json()["status"] == "unassigned"
    assert response.json()["priority_score"] == 20
    assert response.json()["detections"][0]["review_state"] == "needs_review"
    assert api.cases["new-case"].detections[0].review_state == ReviewState.NEEDS_REVIEW


def test_create_case_auto_accepts_at_review_threshold(client):
    payload = create_payload(detections=[create_payload()["detections"][0] | {"confidence": 0.7}])
    response = client.post("/cases", json=payload)
    assert response.status_code == 201
    assert response.json()["detections"][0]["review_state"] == "auto_accepted"
    assert response.json()["priority_score"] == 20


def test_create_case_rejects_duplicate_and_domain_invalid_input(client):
    api.cases["new-case"] = Case("new-case")
    duplicate = client.post("/cases", json=create_payload())
    assert duplicate.status_code == 409
    invalid = client.post("/cases", json=create_payload(case_id="   "))
    assert invalid.status_code == 422


def test_create_case_does_not_accept_internal_fields(client):
    response = client.post("/cases", json=create_payload(priority_score=100, status="completed"))
    assert response.status_code == 422
    assert api.cases == {}


def test_dispatch_calls_domain_and_get_reflects_change(client, monkeypatch):
    case = Case("c1")
    api.cases[case.case_id] = case
    dispatch_spy = Mock(wraps=api.logic.dispatch_case)
    monkeypatch.setattr(api.logic, "dispatch_case", dispatch_spy)
    response = client.post("/cases/c1/dispatch")
    assert response.status_code == 200
    dispatch_spy.assert_called_once_with(case)
    assert case.status == CaseStatus.DISPATCHED
    assert response.json()["status"] == "dispatched"
    assert client.get("/cases").json() == [response.json()]


def test_api_does_not_duplicate_transition(client, monkeypatch):
    case = Case("c1")
    api.cases[case.case_id] = case
    domain_stub = Mock()  # No mutation: API must not perform it itself.
    monkeypatch.setattr(api.logic, "dispatch_case", domain_stub)
    response = client.post("/cases/c1/dispatch")
    assert response.status_code == 200
    domain_stub.assert_called_once_with(case)
    assert case.status == CaseStatus.UNASSIGNED
    assert response.json()["status"] == "unassigned"


def test_missing_case(client, monkeypatch):
    domain_stub = Mock()
    monkeypatch.setattr(api.logic, "dispatch_case", domain_stub)
    response = client.post("/cases/missing/dispatch")
    assert response.status_code == 404
    assert "missing" in response.json()["detail"]
    domain_stub.assert_not_called()


@pytest.mark.parametrize("status", [s for s in CaseStatus if s != CaseStatus.UNASSIGNED])
def test_illegal_dispatch(client, status):
    case = Case("c1", status=status)
    api.cases[case.case_id] = case
    before = deepcopy(case)
    response = client.post("/cases/c1/dispatch")
    assert response.status_code == 409
    assert response.json() == {"detail": f"dispatch_case requires unassigned; current status is {status.value}"}
    assert case == before


def test_start_and_finish_with_zero_payment(client):
    case = Case("c1", [pending_detection()])
    api.cases["c1"] = case
    assert client.post("/cases/c1/dispatch").json()["status"] == "dispatched"
    assert client.post("/cases/c1/start-processing").json()["status"] == "processing"
    review = client.post("/cases/c1/detections/d1/review", json={"result": "confirmed"})
    assert review.status_code == 200
    response = client.post("/cases/c1/finish-processing")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_finish_positive_payment_enters_pending_payment(client):
    case = Case("c1", [pending_detection()], status=CaseStatus.PROCESSING, payment_amount=2400)
    api.cases["c1"] = case
    client.post("/cases/c1/detections/d1/review", json={"result": "confirmed"})
    response = client.post("/cases/c1/finish-processing")
    assert response.status_code == 200
    assert response.json()["status"] == "pending_payment"
    assert response.json()["payment_amount"] == 2400


@pytest.mark.parametrize("amount", [0, 2400])
def test_finish_pending_review_is_conflict_and_atomic(client, amount):
    case = Case("c1", [pending_detection()], status=CaseStatus.PROCESSING, payment_amount=amount)
    api.cases["c1"] = case
    before = deepcopy(case)
    response = client.post("/cases/c1/finish-processing")
    assert response.status_code == 409
    assert "still need review" in response.json()["detail"]
    assert case == before


def test_complete_without_action(client):
    api.cases["c1"] = Case("c1")
    response = client.post("/cases/c1/complete-without-action")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_payment_update_and_locking(client):
    case = Case("c1")
    api.cases["c1"] = case
    response = client.put("/cases/c1/payment", json={"amount": 2400})
    assert response.status_code == 200
    assert response.json()["payment_amount"] == 2400
    case.status = CaseStatus.PENDING_PAYMENT
    assert client.put("/cases/c1/payment", json={"amount": 10}).status_code == 409
    case.status = CaseStatus.COMPLETED
    assert client.put("/cases/c1/payment", json={"amount": 10}).status_code == 409


@pytest.mark.parametrize("amount", [-1, True, 2.5, "2400"])
def test_payment_payload_requires_a_nonnegative_integer(client, amount):
    api.cases["c1"] = Case("c1")
    response = client.put("/cases/c1/payment", json={"amount": amount})
    assert response.status_code == 422
    assert api.cases["c1"].payment_amount == 0


def test_confirm_payment(client):
    api.cases["c1"] = Case("c1", status=CaseStatus.PENDING_PAYMENT, payment_amount=2400)
    response = client.post("/cases/c1/confirm-payment")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["payment_amount"] == 2400


@pytest.mark.parametrize("result,expected_state,score", [
    ("confirmed", "confirmed", 20),
    ("rejected", "rejected", None),
    ("corrected", "corrected", 35),
])
def test_review_detection(client, result, expected_state, score):
    api.cases["c1"] = Case("c1", [pending_detection()])
    body = {"result": result, "review_note": "staff review"}
    if result == "corrected":
        body |= {"reviewed_category": "cleanliness", "reviewed_severity": "moderate"}
    response = client.post("/cases/c1/detections/d1/review", json=body)
    assert response.status_code == 200
    detection = response.json()["detections"][0]
    assert detection["review_state"] == expected_state
    assert detection["review_note"] == "staff review"
    assert response.json()["priority_score"] == score
    if result != "corrected":
        assert detection["reviewed_category"] is None
        assert detection["reviewed_severity"] is None


def test_invalid_corrected_payload_is_validation_error(client):
    api.cases["c1"] = Case("c1", [pending_detection()])
    response = client.post("/cases/c1/detections/d1/review", json={
        "result": "corrected", "reviewed_category": "cleanliness",
    })
    assert response.status_code == 422
    assert api.cases["c1"].detections[0].review_state == ReviewState.NEEDS_REVIEW


def test_appeal_preserves_context_and_uses_original_score(client):
    detection = pending_detection(
        review_state=ReviewState.CORRECTED,
        reviewed_category=ConditionCategory.COLLISION_DAMAGE,
        reviewed_severity=Severity.SEVERE,
        review_note="previous correction",
    )
    case = Case("c1", [detection], status=CaseStatus.DISPATCHED, payment_amount=2400)
    logic.calculate_priority(case, api.demo_policy())
    api.cases["c1"] = case
    response = client.post("/cases/c1/detections/d1/appeal")
    assert response.status_code == 200
    returned = response.json()["detections"][0]
    assert returned["review_state"] == "needs_review"
    assert returned["reviewed_category"] == "collision_damage"
    assert returned["reviewed_severity"] == "severe"
    assert returned["review_note"] == "previous correction"
    assert response.json()["priority_score"] == 20
    assert response.json()["status"] == "dispatched"
    assert response.json()["payment_amount"] == 2400


@pytest.mark.parametrize("path", [
    "/cases/missing/start-processing",
    "/cases/missing/detections/d1/review",
    "/cases/missing/detections/d1/appeal",
])
def test_unknown_case_errors(client, path):
    response = client.post(path, json={"result": "confirmed"} if path.endswith("review") else None)
    assert response.status_code == 404


@pytest.mark.parametrize("path", [
    "/cases/c1/detections/missing/review",
    "/cases/c1/detections/missing/appeal",
])
def test_unknown_detection_errors(client, path):
    api.cases["c1"] = Case("c1", [pending_detection()])
    response = client.post(path, json={"result": "confirmed"} if path.endswith("review") else None)
    assert response.status_code == 409


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:3000"])
def test_development_cors(client, origin):
    response = client.options("/cases/c1/dispatch", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers


def test_development_cors_allows_payment_put(client):
    response = client.options("/cases/c1/payment", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT",
    })
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_other_origins_not_allowed(client):
    response = client.get("/cases", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_only_requested_endpoints_in_openapi(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths) == {
        "/cases", "/cases/{case_id}", "/cases/{case_id}/dispatch",
        "/cases/{case_id}/start-processing", "/cases/{case_id}/finish-processing",
        "/cases/{case_id}/complete-without-action", "/cases/{case_id}/payment",
        "/cases/{case_id}/confirm-payment",
        "/cases/{case_id}/detections/{detection_id}/review",
        "/cases/{case_id}/detections/{detection_id}/appeal",
    }
    assert set(paths["/cases"]) == {"get", "post"}
    assert set(paths["/cases/{case_id}/payment"]) == {"put"}
    assert client.get("/docs").status_code == 200
