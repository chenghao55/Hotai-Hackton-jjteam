"""Photo HTTP routes owned by Module E."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from module_a import CaptureContext, CaptureSlot, PhotoType
from module_a.coach_image import decode

from backend.schemas.photos import (GuidanceAction, GuidanceCode, GuidanceLevel,
                                    PhotoCheck, PhotoGuidanceResponse, PhotoUploadResponse)
from backend.services.photo_guidance import (ModuleAPhotoGuidanceService,
                                             PhotoGuidanceService, get_photo_guidance_service)
from backend.services.photo_storage import (
    PhotoStorageNotFoundError,
    PhotoStorageService,
    get_photo_storage_service,
)


router = APIRouter()
COACHED_SLOTS = {CaptureSlot.FRONT_LEFT, CaptureSlot.FRONT_RIGHT,
                 CaptureSlot.REAR_LEFT, CaptureSlot.REAR_RIGHT,
                 CaptureSlot.INTERIOR_FRONT, CaptureSlot.INTERIOR_REAR}


def capture_context(photo_type, capture_slot, vehicle_type, session_id, frame_id,
                    entry_side, mode):
    supplied = (vehicle_type, session_id, frame_id)
    if all(value is None for value in supplied):
        return None
    if any(value is None for value in supplied):
        raise HTTPException(status_code=422, detail="vehicle_type, session_id and frame_id are required together")
    try:
        return CaptureContext(photo_type, capture_slot, vehicle_type, session_id,
                              frame_id, entry_side=entry_side, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def uncoached_response(image: bytes) -> PhotoGuidanceResponse:
    try:
        decode(image)
    except (ValueError, OSError, SyntaxError) as exc:
        raise HTTPException(status_code=422, detail="invalid image") from exc
    return PhotoGuidanceResponse(
        accepted=True,
        check=PhotoCheck(level=GuidanceLevel.PASS, code=GuidanceCode.PASS,
                         message="此類照片不適用車角 AI 構圖檢核；照片格式有效，可以拍攝。",
                         action=GuidanceAction.ACCEPT),
    )


async def analyze(service, image, context):
    if context is None:
        # Keep injected legacy test adapters compatible; the real coach rejects absent context.
        if isinstance(service, ModuleAPhotoGuidanceService):
            raise HTTPException(status_code=422, detail="capture context is required")
        return await run_in_threadpool(service.analyze, image)
    if context.capture_slot not in COACHED_SLOTS:
        return await run_in_threadpool(uncoached_response, image)
    try:
        return await run_in_threadpool(service.analyze, image, context)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="photo coach checkpoint is unavailable") from exc
    except (ValueError, OSError, SyntaxError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/photo-guidance", response_model=PhotoGuidanceResponse, response_model_exclude_unset=True)
async def photo_guidance(
    file: UploadFile = File(...),
    photo_type: PhotoType = Form(None),
    capture_slot: CaptureSlot = Form(None),
    vehicle_type: str | None = Form(None),
    session_id: str | None = Form(None),
    frame_id: int | None = Form(None),
    entry_side: str | None = Form(None),
    service: Annotated[PhotoGuidanceService, Depends(get_photo_guidance_service)] = None,
) -> PhotoGuidanceResponse:
    image = await file.read()
    if not image:
        raise HTTPException(status_code=422, detail="image file must not be empty")
    if service and isinstance(service, ModuleAPhotoGuidanceService) and (photo_type is None or capture_slot is None):
        raise HTTPException(status_code=422, detail="photo_type and capture_slot are required")
    context = capture_context(photo_type, capture_slot, vehicle_type, session_id,
                              frame_id, entry_side, "preview")
    return await analyze(service, image, context)


@router.post("/photos", response_model=PhotoUploadResponse, response_model_exclude_unset=True)
async def upload_photo(
    file: UploadFile = File(...),
    photo_type: PhotoType = Form(...),
    capture_slot: CaptureSlot = Form(...),
    vehicle_type: str | None = Form(None),
    session_id: str | None = Form(None),
    frame_id: int | None = Form(None),
    entry_side: str | None = Form(None),
    guidance_service: Annotated[PhotoGuidanceService, Depends(get_photo_guidance_service)] = None,
    storage_service: Annotated[PhotoStorageService, Depends(get_photo_storage_service)] = None,
) -> PhotoUploadResponse:
    image = await file.read()
    if not image:
        raise HTTPException(status_code=422, detail="image file must not be empty")
    mime_type = file.content_type
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise HTTPException(status_code=422, detail="image content type is required")

    context = capture_context(photo_type, capture_slot, vehicle_type, session_id,
                              frame_id, entry_side, "final")
    guidance = await analyze(guidance_service, image, context)
    if not guidance.accepted:
        return PhotoUploadResponse(accepted=False, photo_id=None, check=guidance.check)

    try:
        photo_id = storage_service.save(image, photo_type, capture_slot, mime_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
