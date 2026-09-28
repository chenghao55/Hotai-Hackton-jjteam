"""E-owned configuration and dependency wiring for Module B case building."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from module_b import CaseBuildingModuleB, DamageModelAnalyzer, ModuleB
from module_d import demo_policy


DEFAULT_MODULE_B_CHECKPOINT_PATH = Path("artifacts/module_b/damage_multitask.pth")
DEFAULT_MODULE_B_DEVICE = "auto"


@dataclass(frozen=True)
class ModuleBConfiguration:
    """Runtime configuration for the production Module B dependency."""

    checkpoint_path: Path
    device: str


def get_module_b_configuration() -> ModuleBConfiguration:
    """Read the centralized Module B runtime configuration for this process."""
    configured_path = os.getenv("HOTAI_MODULE_B_CHECKPOINT_PATH")
    configured_device = os.getenv("HOTAI_MODULE_B_DEVICE")
    return ModuleBConfiguration(
        checkpoint_path=Path(configured_path)
        if configured_path
        else DEFAULT_MODULE_B_CHECKPOINT_PATH,
        device=configured_device or DEFAULT_MODULE_B_DEVICE,
    )


@lru_cache(maxsize=1)
def get_case_building_module_b() -> ModuleB:
    """Build and cache the production Module B orchestrator.

    Routes consume this function as a FastAPI dependency. Tests should override
    it with a fake ModuleB, so they do not load the ML checkpoint.
    """
    configuration = get_module_b_configuration()
    analyzer = DamageModelAnalyzer.from_checkpoint(
        configuration.checkpoint_path,
        device=configuration.device,
    )
    return CaseBuildingModuleB(analyzer, policy=demo_policy())


def get_case_building_module_b_provider() -> Callable[[], ModuleB]:
    """Provide lazy Module B construction after a request has been validated."""
    return get_case_building_module_b
