"""FastAPI routers owned by Module E."""

from .cases import router as case_router
from .photos import router as photo_router

__all__ = ["case_router", "photo_router"]
