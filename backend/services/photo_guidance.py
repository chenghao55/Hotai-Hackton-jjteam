"""Replaceable E adapter for live camera-frame shooting guidance."""

from abc import ABC, abstractmethod

from backend.schemas.photos import (
    GuidanceAction,
    GuidanceCode,
    GuidanceLevel,
    PhotoCheck,
    PhotoGuidanceResponse,
)


class PhotoGuidanceService(ABC):
    """Analyzes image bytes and returns the HTTP guidance contract."""

    @abstractmethod
    def analyze(self, image: bytes) -> PhotoGuidanceResponse:
        raise NotImplementedError


class StubPhotoGuidanceService(PhotoGuidanceService):
    """Temporary PASS result until Module A supplies its guidance adapter."""

    def analyze(self, image: bytes) -> PhotoGuidanceResponse:
        return PhotoGuidanceResponse(
            accepted=True,
            check=PhotoCheck(
                level=GuidanceLevel.PASS,
                code=GuidanceCode.PASS,
                message="視角正確，請保持穩定並按下快門。",
                action=GuidanceAction.ACCEPT,
            ),
        )


def get_photo_guidance_service() -> PhotoGuidanceService:
    """FastAPI dependency; replace this provider when Module A is available."""
    return StubPhotoGuidanceService()
