from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from module_d import api
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
            "review_state": "needs_review", "reviewed_category": None,
            "reviewed_severity": None, "review_note": None,
        }],
    }]
    assert case == before


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


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:3000"])
def test_development_cors(client, origin):
    response = client.options("/cases/c1/dispatch", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers


def test_other_origins_not_allowed(client):
    response = client.get("/cases", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_only_requested_endpoints_in_openapi(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths) == {
        "/cases",
        "/cases/{case_id}/dispatch",
        "/photos",
        "/photos/{photo_id}",
    }
    assert set(paths["/cases"]) == {"get"}
    assert set(paths["/cases/{case_id}/dispatch"]) == {"post"}
    assert client.get("/docs").status_code == 200
