"""Domain data and constructor validation; no workflow operations yet."""

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


class ConditionCategory(str, Enum):
    SCRATCH = "scratch"
    COLLISION_DAMAGE = "collision_damage"
    CLEANLINESS = "cleanliness"


class Severity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


class ReviewState(str, Enum):
    """
    detection的審核狀態，是否需人工修正等等
    """

    NEEDS_REVIEW = "needs_review" # AI 有看到東西，但信心不夠，需要人看
    AUTO_ACCEPTED = "auto_accepted" # AI 信心夠高，系統先自動接受
    CONFIRMED = "confirmed" # 人工看過後，確認 AI 原本判斷是對的
    REJECTED = "rejected" # 人工看過後，認為這個 Detection 根本不成立
    CORRECTED = "corrected" # 人工看過後，認為有這個問題，但 AI 的 category 或 severity 要修正


class CaseStatus(str, Enum):
    UNASSIGNED = "unassigned"
    DISPATCHED = "dispatched"
    PROCESSING = "processing"
    PENDING_PAYMENT = "pending_payment"
    COMPLETED = "completed"


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _enum(value: object, enum_type: type[Enum], name: str) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{name} must be a {enum_type.__name__}")


def _probability(value: float, name: str) -> None:
    if (type(value) not in (int, float) or not 0 <= value <= 1
            or not isfinite(value)):
        raise ValueError(f"{name} must be a finite number within [0, 1]")


@dataclass
class Detection:
    detection_id: str
    photo_id: str
    category: ConditionCategory
    severity: Severity
    confidence: float
    review_state: ReviewState
    reviewed_category: ConditionCategory | None = None
    reviewed_severity: Severity | None = None
    review_note: str | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        _identifier(self.detection_id, "detection_id")
        _identifier(self.photo_id, "photo_id")
        _enum(self.category, ConditionCategory, "category")
        _enum(self.severity, Severity, "severity")
        _probability(self.confidence, "confidence")
        _enum(self.review_state, ReviewState, "review_state")
        if self.review_note is not None and not isinstance(self.review_note, str):
            raise ValueError("review_note must be a string or None")
        if self.review_state == ReviewState.CORRECTED:
            _enum(self.reviewed_category, ConditionCategory, "reviewed_category")
            _enum(self.reviewed_severity, Severity, "reviewed_severity")
            if (self.reviewed_category, self.reviewed_severity) == (self.category, self.severity):
                raise ValueError("CORRECTED requires a category or severity change")
        elif self.reviewed_category is not None or self.reviewed_severity is not None:
            raise ValueError("Only CORRECTED detections may contain reviewed values")


@dataclass
class Case:
    case_id: str
    detections: list[Detection] = field(default_factory=list)
    priority_score: int | None = None  # Maintenance priority score from 0 to 100; None is uncalculated.
    status: CaseStatus = CaseStatus.UNASSIGNED
    payment_amount: int = 0

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        _identifier(self.case_id, "case_id")
        if not isinstance(self.detections, list):
            raise ValueError("detections must be a list of Detection objects")
        ids = set()
        for detection in self.detections:
            if not isinstance(detection, Detection):
                raise ValueError("detections must contain only Detection objects")
            detection.validate()
            if detection.detection_id in ids:
                raise ValueError("detection_id must be unique within a Case")
            ids.add(detection.detection_id)
        if self.priority_score is not None:
            if type(self.priority_score) is not int or not 0 <= self.priority_score <= 100:
                raise ValueError("priority_score must be an integer within [0, 100] or None")
        _enum(self.status, CaseStatus, "status")
        if type(self.payment_amount) is not int or self.payment_amount < 0:
            raise ValueError("payment_amount must be a nonnegative integer NTD amount")
