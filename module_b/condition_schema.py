"""Shared constants for the experimental vehicle-condition model."""

from typing import Final


CATEGORY_ORDER: Final[tuple[str, ...]] = (
    "scratch",
    "collision_damage",
)

# Present the most operationally important finding first.
OUTPUT_ORDER: Final[tuple[str, ...]] = (
    "collision_damage",
    "scratch",
)

SEVERITY_BY_CATEGORY: Final[dict[str, str]] = {
    "scratch": "moderate",
    "collision_damage": "severe",
}

REVIEW_STATE: Final[str] = "needs_review"
TASK_NAME: Final[str] = "vehicle_damage_detection"
MODEL_STATUS: Final[str] = "experimental_review_only"
