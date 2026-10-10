"""HTTP-only contracts for camera guidance and accepted photo uploads."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class GuidanceLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
    L6 = "L6"
    PASS = "PASS"


class GuidanceCode(str, Enum):
    TOO_DARK = "TOO_DARK"
    BACKLIGHT = "BACKLIGHT"
    OVEREXPOSED = "OVEREXPOSED"
    BLUR = "BLUR"
    LOW_DETAIL = "LOW_DETAIL"
    SUBJECT_NOT_DETECTED = "SUBJECT_NOT_DETECTED"
    MULTIPLE_SUBJECTS = "MULTIPLE_SUBJECTS"
    SUBJECT_NEAR_EDGE = "SUBJECT_NEAR_EDGE"
    SUBJECT_TOO_SMALL = "SUBJECT_TOO_SMALL"
    SUBJECT_TOO_LARGE = "SUBJECT_TOO_LARGE"
    TOO_FAR = "TOO_FAR"
    TOO_CLOSE = "TOO_CLOSE"
    OFF_CENTER = "OFF_CENTER"
    ANGLE_TOO_HIGH = "ANGLE_TOO_HIGH"
    ANGLE_TOO_LOW = "ANGLE_TOO_LOW"
    TOO_FRONT = "TOO_FRONT"
    TOO_SIDE = "TOO_SIDE"
    INTERIOR_NOT_ALIGNED = "INTERIOR_NOT_ALIGNED"
    POSSIBLE_WRONG_SLOT = "POSSIBLE_WRONG_SLOT"
    MISSING_REQUIRED_FEATURE = "MISSING_REQUIRED_FEATURE"
    GEOMETRY_MISMATCH = "GEOMETRY_MISMATCH"
    AMBIGUOUS_TEMPLATES = "AMBIGUOUS_TEMPLATES"
    UNSUPPORTED_SLOT = "UNSUPPORTED_SLOT"
    TEMPLATE_NOT_CALIBRATED = "TEMPLATE_NOT_CALIBRATED"
    FRONT_SEAT_EVIDENCE_UNAVAILABLE = "FRONT_SEAT_EVIDENCE_UNAVAILABLE"
    PASS = "PASS"


class VehicleType(str, Enum):
    SEDAN = "sedan"
    SUV = "suv"


class EntrySide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


class GuidanceAction(str, Enum):
    GUIDE = "guide"
    RESHOOT = "reshoot"
    ACCEPT = "accept"


class PhotoCheck(BaseModel):
    level: GuidanceLevel
    code: GuidanceCode
    message: str = Field(min_length=1)
    action: GuidanceAction


class _PhotoDecisionResponse(BaseModel):
    accepted: bool
    check: PhotoCheck

    @model_validator(mode="after")
    def accepted_matches_check(self) -> "_PhotoDecisionResponse":
        if self.accepted:
            if (
                self.check.level != GuidanceLevel.PASS
                or self.check.code != GuidanceCode.PASS
                or self.check.action != GuidanceAction.ACCEPT
            ):
                raise ValueError("accepted responses require a PASS check with action=accept")
        elif (
            self.check.level == GuidanceLevel.PASS
            or self.check.code == GuidanceCode.PASS
            or self.check.action == GuidanceAction.ACCEPT
        ):
            raise ValueError("rejected responses cannot declare PASS or action=accept")
        return self


class PhotoGuidanceResponse(_PhotoDecisionResponse):
    """Result of a live-frame check; no photo is stored."""


class PhotoUploadResponse(_PhotoDecisionResponse):
    """Result of final photo validation and, if accepted, storage."""

    photo_id: str | None

    @model_validator(mode="after")
    def photo_id_matches_acceptance(self) -> "PhotoUploadResponse":
        if self.accepted:
            if not isinstance(self.photo_id, str) or not self.photo_id.strip():
                raise ValueError("accepted uploads require a nonempty photo_id")
        elif self.photo_id is not None:
            raise ValueError("rejected uploads must have photo_id=None")
        return self


class DevelopmentForceSaveResponse(BaseModel):
    """Development-only storage result; this is not a PhotoCoach decision."""

    photo_id: str = Field(min_length=1)
