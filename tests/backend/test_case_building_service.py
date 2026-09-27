from pathlib import Path

from backend.services import case_building


def test_module_b_runtime_configuration_uses_central_environment_variables(monkeypatch):
    monkeypatch.setenv("HOTAI_MODULE_B_CHECKPOINT_PATH", "configured/model.pth")
    monkeypatch.setenv("HOTAI_MODULE_B_DEVICE", "cpu")

    configuration = case_building.get_module_b_configuration()

    assert configuration.checkpoint_path == Path("configured/model.pth")
    assert configuration.device == "cpu"


def test_module_b_provider_is_lazy(monkeypatch):
    def fake_builder():
        raise AssertionError("the provider must not construct Module B itself")

    monkeypatch.setattr(case_building, "get_case_building_module_b", fake_builder)

    assert case_building.get_case_building_module_b_provider() is fake_builder
