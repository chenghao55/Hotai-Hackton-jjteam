"""HTTP-only request schemas for Module D Case operations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from module_d.models import ConditionCategory, ReviewState, Severity


class DetectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detection_id: str
    borrow_photo_id: str
    return_photo_id: str
    category: ConditionCategory
    severity: Severity
    confidence: float


class CaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    detections: list[DetectionCreateRequest]


class CaseFromPhotosRequest(BaseModel):
    """Production Case-creation request using previously accepted photo IDs."""

    model_config = ConfigDict(extra="forbid")

    photo_ids: list[str] = Field(min_length=1)

    @field_validator("photo_ids")
    @classmethod
    def photo_ids_must_be_unique_nonempty_strings(cls, photo_ids: list[str]) -> list[str]:
        if any(not photo_id.strip() for photo_id in photo_ids):
            raise ValueError("photo_ids must contain only nonempty strings")
        if len(set(photo_ids)) != len(photo_ids):
            raise ValueError("photo_ids must be unique")
        return photo_ids


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: StrictInt = Field(ge=0)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: Literal[
        ReviewState.CONFIRMED,
        ReviewState.REJECTED,
        ReviewState.CORRECTED,
    ]
    reviewed_category: ConditionCategory | None = None
    reviewed_severity: Severity | None = None
    review_note: str | None = None

    @model_validator(mode="after")
    def corrected_review_requires_both_values(self) -> "ReviewRequest":
        if self.result == ReviewState.CORRECTED:
            if self.reviewed_category is None or self.reviewed_severity is None:
                raise ValueError("CORRECTED requires reviewed_category and reviewed_severity")
        return self
