"""Case HTTP routes owned by Module E."""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from backend.schemas.cases import CaseCreateRequest, PaymentRequest, ReviewRequest
from backend.state.cases import cases
from module_d import logic
from module_d.models import Case, Detection, ReviewState
from module_d.policy import demo_policy


router = APIRouter()


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


@router.get("/cases", response_model=list[Case])
async def list_cases() -> list[Case]:
    return list(cases.values())


@router.get("/cases/{case_id}", response_model=Case)
async def get_case(case_id: str) -> Case:
    return _case_or_404(case_id)


@router.post("/cases", response_model=Case, status_code=201)
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


@router.post("/cases/{case_id}/dispatch", response_model=Case)
async def dispatch(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.dispatch_case(case))
    return case


@router.post("/cases/{case_id}/start-processing", response_model=Case)
async def start_processing(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.start_processing(case))
    return case


@router.post("/cases/{case_id}/finish-processing", response_model=Case)
async def finish_processing(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.finish_processing(case))
    return case


@router.post("/cases/{case_id}/complete-without-action", response_model=Case)
async def complete_without_action(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.complete_without_action(case))
    return case


@router.put("/cases/{case_id}/payment", response_model=Case)
async def update_payment(case_id: str, request: PaymentRequest) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.set_payment_amount(case, request.amount))
    return case


@router.post("/cases/{case_id}/confirm-payment", response_model=Case)
async def confirm_payment(case_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.confirm_payment(case))
    return case


@router.post("/cases/{case_id}/detections/{detection_id}/review", response_model=Case)
async def review_detection(case_id: str, detection_id: str, request: ReviewRequest) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(
        lambda: logic.apply_review(
            case,
            detection_id,
            request.result,
            policy=demo_policy(),
            reviewed_category=request.reviewed_category,
            reviewed_severity=request.reviewed_severity,
            review_note=request.review_note,
        )
    )
    return case


@router.post("/cases/{case_id}/detections/{detection_id}/appeal", response_model=Case)
async def appeal_detection(case_id: str, detection_id: str) -> Case:
    case = _case_or_404(case_id)
    _domain_conflict(lambda: logic.appeal_detection(case, detection_id, policy=demo_policy()))
    return case
