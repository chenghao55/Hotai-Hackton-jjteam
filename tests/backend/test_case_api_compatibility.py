from backend.state.cases import cases
from module_d import api as legacy_api


def test_legacy_module_d_api_mounts_canonical_case_router_and_shared_state():
    assert legacy_api.cases is cases
    paths = legacy_api.app.openapi()["paths"]
    assert "/cases" in paths
    assert "/cases/{case_id}/dispatch" in paths
