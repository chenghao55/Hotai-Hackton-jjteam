"""Minimal development API; all state is process-local and temporary."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import logic
from .models import Case, ConditionCategory, Detection, ReviewState, Severity
from .policy import demo_policy


app = FastAPI()

# Development only: explicit local UI origins, no credentialed requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

_demo_case = Case("demo-001", [Detection(
    detection_id="demo-detection-001",
    borrow_photo_id="demo-borrow-001",
    return_photo_id="demo-return-001",
    category=ConditionCategory.SCRATCH,
    severity=Severity.MINOR,
    confidence=0.9,
    review_state=ReviewState.NEEDS_REVIEW,
)])
_demo_policy = demo_policy()
logic.assess_detection(_demo_case.detections[0], _demo_policy)
logic.calculate_priority(_demo_case, _demo_policy)
cases: dict[str, Case] = {_demo_case.case_id: _demo_case}


@app.get("/cases", response_model=list[Case])
async def list_cases() -> list[Case]:
    return list(cases.values())


@app.post("/cases/{case_id}/dispatch", response_model=Case)
async def dispatch(case_id: str) -> Case:
    case = cases.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown case_id: {case_id!r}")
    try:
        logic.dispatch_case(case)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return case
