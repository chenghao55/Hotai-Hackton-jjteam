"""Public output contracts for Module B."""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class PhotoClaimResult:
    """A single image's model score and thresholded claim label."""

    photo_id: str
    claim_probability: float
    predicted_label: Literal["claim", "no_claim"]
    model_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.photo_id, str) or not self.photo_id.strip():
            raise ValueError("photo_id must be a nonempty string")
        if (
            type(self.claim_probability) is not float
            or not isfinite(self.claim_probability)
            or not 0.0 <= self.claim_probability <= 1.0
        ):
            raise ValueError("claim_probability must be a finite float within [0, 1]")
        if self.predicted_label not in {"claim", "no_claim"}:
            raise ValueError("predicted_label must be 'claim' or 'no_claim'")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("model_version must be a nonempty string")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
