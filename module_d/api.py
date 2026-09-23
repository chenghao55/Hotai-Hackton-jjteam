"""Compatibility app for legacy imports; canonical Case HTTP code lives in backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.cases import (
    appeal_detection,
    complete_without_action,
    confirm_payment,
    create_case,
    dispatch,
    finish_processing,
    get_case,
    list_cases,
    review_detection,
    router,
    start_processing,
    update_payment,
)
from backend.schemas.cases import (
    CaseCreateRequest,
    DetectionCreateRequest,
    PaymentRequest,
    ReviewRequest,
)
from backend.state.cases import cases

from . import logic
from .policy import demo_policy


app = FastAPI()

# Development-only compatibility configuration until backend/main.py exists.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
app.include_router(router)


__all__ = [
    "CaseCreateRequest",
    "DetectionCreateRequest",
    "PaymentRequest",
    "ReviewRequest",
    "appeal_detection",
    "app",
    "cases",
    "complete_without_action",
    "confirm_payment",
    "create_case",
    "dispatch",
    "finish_processing",
    "get_case",
    "list_cases",
    "review_detection",
    "start_processing",
    "update_payment",
]
