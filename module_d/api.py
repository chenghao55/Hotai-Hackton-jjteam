"""Development API adapter; all state is process-local and temporary."""

from collections.abc import Callable
from typing import Literal

from functools import lru_cache
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from . import logic
from .models import Case, ConditionCategory, Detection, ReviewState, Severity
from .policy import demo_policy
from module_a import PhotoNotFoundError, PhotoType, get_photo, get_photo_info, save_photo


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
class PhotoUploadResponse(BaseModel):
    photo_id: str


class CaseCreateRequest(BaseModel):
    case_id: str = Field(min_length=1)
    borrow_photo_id: str = Field(min_length=1)
    return_photo_id: str = Field(min_length=1)

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
    source_photo_id="demo-return-001",
    category=ConditionCategory.SCRATCH,
    severity=Severity.MINOR,
    confidence=0.5,
    review_state=ReviewState.NEEDS_REVIEW,
)])
_demo_policy = demo_policy()
logic.assess_detection(_demo_case.detections[0], _demo_policy)
logic.calculate_priority(_demo_case, _demo_policy)
cases: dict[str, Case] = {_demo_case.case_id: _demo_case}


@lru_cache(maxsize=1)
def get_case_builder():
    """Load the deployment checkpoint once, on the first analysis request."""
    from module_b import CaseBuildingModuleB, DamageModelAnalyzer

    default_checkpoint = (
        Path(__file__).resolve().parent.parent
        / "artifacts"
        / "module_b"
        / "damage_multitask.pth"
    )
    checkpoint_path = Path(os.environ.get("MODULE_B_CHECKPOINT", default_checkpoint))
    device = os.environ.get("MODULE_B_DEVICE", "auto")
    analyzer = DamageModelAnalyzer.from_checkpoint(checkpoint_path, device=device)
    return CaseBuildingModuleB(analyzer, policy=_demo_policy)


@app.post("/photos", response_model=PhotoUploadResponse, status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    photo_type: PhotoType = Form(...),
) -> PhotoUploadResponse:
    mime_type = file.content_type
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise HTTPException(status_code=422, detail="file content type is required")
    photo_id = save_photo(await file.read(), photo_type, mime_type)
    return PhotoUploadResponse(photo_id=photo_id)


@app.get("/photos/{photo_id}")
async def download_photo(photo_id: str) -> Response:
    try:
        info = get_photo_info(photo_id)
        content = get_photo(photo_id)
    except PhotoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=content, media_type=info.mime_type)


@app.get("/cases", response_model=list[Case])
async def list_cases() -> list[Case]:
    """get all cases as list"""
    return list(cases.values())


@app.post("/cases", response_model=Case, status_code=201)
async def create_analyzed_case(request: CaseCreateRequest) -> Case:
    if request.case_id in cases:
        raise HTTPException(
            status_code=409,
            detail=f"Case already exists: {request.case_id!r}",
        )

    try:
        borrow_info = get_photo_info(request.borrow_photo_id)
        return_info = get_photo_info(request.return_photo_id)
        borrow_bytes = get_photo(request.borrow_photo_id)
        return_bytes = get_photo(request.return_photo_id)
    except PhotoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if borrow_info.photo_type != PhotoType.BORROW:
        raise HTTPException(status_code=422, detail="borrow_photo_id must reference a borrow photo")
    if return_info.photo_type != PhotoType.RETURN:
        raise HTTPException(status_code=422, detail="return_photo_id must reference a return photo")

    try:
        builder = get_case_builder()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Module B model is unavailable") from exc

    try:
        case = builder.analyze(
            request.case_id,
            [
                (request.borrow_photo_id, borrow_bytes),
                (request.return_photo_id, return_bytes),
            ],
        )
    except ValueError as exc:
        from module_b.dataset import ImageDecodeError

        if isinstance(exc, ImageDecodeError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=503, detail="Module B inference failed") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Module B inference failed") from exc

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
