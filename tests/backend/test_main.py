from collections import Counter

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import case_router, photo_router
from backend.state.cases import cases
from module_d import api as legacy_api


client = TestClient(app)


def _registered_route_methods(application: FastAPI) -> list[tuple[str, str]]:
    return [
        (path, method.upper())
        for path, path_item in application.openapi()["paths"].items()
        for method in path_item
    ]


def test_backend_main_app_can_be_imported() -> None:
    assert isinstance(app, FastAPI)


def test_photo_routes_are_registered() -> None:
    registered = set(_registered_route_methods(app))

    assert ("/photo-guidance", "POST") in registered
    assert ("/photos", "POST") in registered
    assert ("/photos/{photo_id}", "GET") in registered


def test_case_routes_are_registered() -> None:
    registered = set(_registered_route_methods(app))

    expected = {
        ("/cases", "GET"),
        ("/cases", "POST"),
        ("/cases/from-photos", "POST"),
        ("/cases/{case_id}", "GET"),
        ("/cases/{case_id}/dispatch", "POST"),
        ("/cases/{case_id}/start-processing", "POST"),
        ("/cases/{case_id}/finish-processing", "POST"),
        ("/cases/{case_id}/payment", "PUT"),
        ("/cases/{case_id}/confirm-payment", "POST"),
        ("/cases/{case_id}/complete-without-action", "POST"),
        ("/cases/{case_id}/detections/{detection_id}/review", "POST"),
        ("/cases/{case_id}/detections/{detection_id}/appeal", "POST"),
    }

    assert expected <= registered


def test_get_cases_works_through_canonical_app() -> None:
    original_cases = cases.copy()
    cases.clear()
    try:
        response = client.get("/cases")
    finally:
        cases.clear()
        cases.update(original_cases)

    assert response.status_code == 200
    assert response.json() == []


def test_photo_guidance_works_through_canonical_app() -> None:
    response = client.post(
        "/photo-guidance",
        files={"file": ("vehicle.jpg", b"image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_module_d_api_app_reuses_canonical_app() -> None:
    assert legacy_api.app is app
    assert TestClient(legacy_api.app).get("/cases").status_code == 200


def test_routes_are_not_registered_more_than_once() -> None:
    included_routers = [
        route.original_router
        for route in app.routes
        if hasattr(route, "original_router")
    ]
    router_counts = Counter(id(router) for router in included_routers)

    assert router_counts == Counter({id(photo_router): 1, id(case_router): 1})


def test_development_cors_is_applied_by_canonical_app() -> None:
    response = client.options(
        "/cases/example/payment",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "PUT" in response.headers["access-control-allow-methods"]
