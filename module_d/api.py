"""Legacy compatibility imports for the canonical Module E application."""

from backend.main import app
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
