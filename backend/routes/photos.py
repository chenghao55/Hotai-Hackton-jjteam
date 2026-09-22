"""Photo HTTP routes owned by Module E."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.schemas.photos import PhotoGuidanceResponse
from backend.services.photo_guidance import PhotoGuidanceService, get_photo_guidance_service


router = APIRouter()


@router.post("/photo-guidance", response_model=PhotoGuidanceResponse)
async def photo_guidance(
    file: UploadFile = File(...),
    service: Annotated[PhotoGuidanceService, Depends(get_photo_guidance_service)] = None,
) -> PhotoGuidanceResponse:
    image = await file.read()
    if not image:
        raise HTTPException(status_code=422, detail="image file must not be empty")
    return service.analyze(image)
