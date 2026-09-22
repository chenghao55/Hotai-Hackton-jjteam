"""Development API adapter; all state is process-local and temporary."""

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from . import logic
from .models import Case, ConditionCategory, Detection, ReviewState, Severity
from .policy import demo_policy


app = FastAPI()


class DetectionCreateRequest(BaseModel):
    """DetectionCreateRequest必須要符合此格式"""

    model_config = ConfigDict(extra="forbid")

    detection_id: str
    borrow_photo_id: str
    return_photo_id: str
    category: ConditionCategory
    severity: Severity
    confidence: float


class CaseCreateRequest(BaseModel):
    """Case Create Request必須要符合此格式"""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    detections: list[DetectionCreateRequest]


class PaymentRequest(BaseModel):
    """Payment Request必須要符合此格式"""
    model_config = ConfigDict(extra="forbid")

    amount: StrictInt = Field(ge=0)


class ReviewRequest(BaseModel):
    """Review Request必須要符合此格式"""
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
# Development only: explicit local UI origins, no credentialed requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

_demo_case = Case("demo-001", [Detection(
    detection_id="demo-detection-001",
    borrow_photo_id="demo-borrow-001",
    return_photo_id="demo-return-001",
    category=ConditionCategory.SCRATCH,
    severity=Severity.MINOR,
    confidence=0.5,
    review_state=ReviewState.NEEDS_REVIEW,
)])
_demo_policy = demo_policy()
logic.assess_detection(_demo_case.detections[0], _demo_policy)
logic.calculate_priority(_demo_case, _demo_policy)
cases: dict[str, Case] = {_demo_case.case_id: _demo_case}


def _case_or_404(case_id: str) -> Case:
    case = cases.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown case_id: {case_id!r}")
    return case


def _domain_conflict(operation: Callable[[], None]) -> None:
    try:
        operation()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _invalid_create(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


@app.get("/cases", response_model=list[Case])
async def list_cases() -> list[Case]:
    """get all cases as list"""
    return list(cases.values())


@app.get("/cases/{case_id}", response_model=Case)
async def get_case(case_id: str) -> Case:
    return _case_or_404(case_id)


@app.post("/cases", response_model=Case, status_code=201)
async def create_case(request: CaseCreateRequest) -> Case:
    if request.case_id in cases:
        raise HTTPException(status_code=409, detail=f"Case already exists: {request.case_id!r}")
    try:
        detections = [
            Detection(
                detection_id=item.detection_id,
                borrow_photo_id=item.borrow_photo_id,
                return_photo_id=item.return_photo_id,
                category=item.category,
                severity=item.severity,
                confidence=item.confidence,
                review_state=ReviewState.NEEDS_REVIEW,
            )
            for item in request.detections
        ]
        case = Case(case_id=request.case_id, detections=detections)
        policy = demo_policy()
        for detection in case.detections:
            logic.assess_detection(detection, policy)
        logic.calculate_priority(case, policy)
    except ValueError as exc:
        raise _invalid_create(str(exc)) from exc
    cases[case.case_id] = case
    return case


@app.post("/cases/{case_id}/dispatch", response_model=Case)
async def dispatch(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.dispatch_case(case))
    return case


@app.post("/cases/{case_id}/start-processing", response_model=Case)
async def start_processing(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.start_processing(case))
    return case


@app.post("/cases/{case_id}/finish-processing", response_model=Case)
async def finish_processing(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.finish_processing(case))
    return case


@app.post("/cases/{case_id}/complete-without-action", response_model=Case)
async def complete_without_action(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.complete_without_action(case))
    return case


@app.put("/cases/{case_id}/payment", response_model=Case)
async def update_payment(case_id: str, request: PaymentRequest) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.set_payment_amount(case, request.amount))
    return case


@app.post("/cases/{case_id}/confirm-payment", response_model=Case)
async def confirm_payment(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.confirm_payment(case))
    return case


@app.post("/cases/{case_id}/detections/{detection_id}/review", response_model=Case)
async def review_detection(case_id: str, detection_id: str, request: ReviewRequest) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.apply_review(
        case,
        detection_id,
        request.result,
        policy=demo_policy(),
        reviewed_category=request.reviewed_category,
        reviewed_severity=request.reviewed_severity,
        review_note=request.review_note,
    ))
    return case


@app.post("/cases/{case_id}/detections/{detection_id}/appeal", response_model=Case)
async def appeal_detection(case_id: str, detection_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.appeal_detection(case, detection_id, policy=demo_policy()))
    return case
