"""Photo HTTP routes owned by Module E."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from module_a import PhotoType

from backend.schemas.photos import PhotoGuidanceResponse, PhotoUploadResponse
from backend.services.photo_guidance import PhotoGuidanceService, get_photo_guidance_service
from backend.services.photo_storage import (
    PhotoStorageNotFoundError,
    PhotoStorageService,
    get_photo_storage_service,
)


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


@router.post("/photos", response_model=PhotoUploadResponse)
async def upload_photo(
    file: UploadFile = File(...),
    photo_type: PhotoType = Form(...),
    guidance_service: Annotated[PhotoGuidanceService, Depends(get_photo_guidance_service)] = None,
    storage_service: Annotated[PhotoStorageService, Depends(get_photo_storage_service)] = None,
) -> PhotoUploadResponse:
    image = await file.read()
    if not image:
        raise HTTPException(status_code=422, detail="image file must not be empty")
    mime_type = file.content_type
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise HTTPException(status_code=422, detail="image content type is required")

    guidance = guidance_service.analyze(image)
    if not guidance.accepted:
        return PhotoUploadResponse(accepted=False, photo_id=None, check=guidance.check)

    photo_id = storage_service.save(image, photo_type, mime_type)
    return PhotoUploadResponse(accepted=True, photo_id=photo_id, check=guidance.check)


@router.get("/photos/{photo_id}")
async def download_photo(
    photo_id: str,
    storage_service: Annotated[PhotoStorageService, Depends(get_photo_storage_service)] = None,
) -> Response:
    try:
        image, info = storage_service.get(photo_id)
    except PhotoStorageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown photo_id: {photo_id!r}") from exc
    return Response(content=image, media_type=info.mime_type)
