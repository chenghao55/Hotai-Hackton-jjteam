"""Photo HTTP routes owned by Module E."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from module_a import CaptureSlot, PhotoType

from backend.schemas.photos import EntrySide, PhotoGuidanceResponse, PhotoUploadResponse, VehicleType
from backend.services.photo_guidance import (
    GuidanceImageSource,
    GuidanceMode,
    PhotoGuidanceContext,
    PhotoGuidanceService,
    UnsupportedGuidanceDecisionError,
    get_photo_guidance_service,
)
from backend.services.photo_storage import (
    PhotoStorageNotFoundError,
    PhotoStorageService,
    get_photo_storage_service,
)


router = APIRouter()


def _guidance_context(
    *,
    photo_type: PhotoType,
    capture_slot: CaptureSlot,
    vehicle_type: VehicleType,
    session_id: str,
    frame_id: int,
    entry_side: EntrySide | None,
    mode: GuidanceMode,
    source: GuidanceImageSource | None,
) -> PhotoGuidanceContext:
    if not session_id.strip():
        raise HTTPException(status_code=422, detail="session_id must not be blank")
    interior = capture_slot in {CaptureSlot.INTERIOR_FRONT, CaptureSlot.INTERIOR_REAR}
    if interior and entry_side is None:
        raise HTTPException(status_code=422, detail="entry_side is required for interior photos")
    if not interior and entry_side is not None:
        raise HTTPException(status_code=422, detail="entry_side is only valid for interior photos")
    return PhotoGuidanceContext(
        photo_type=photo_type,
        capture_slot=capture_slot,
        vehicle_type=vehicle_type,
        session_id=session_id,
        frame_id=frame_id,
        entry_side=entry_side,
        mode=mode,
        image_mirrored=False,
        source=source,
    )


async def _analyze_guidance(
    service: PhotoGuidanceService,
    image: bytes,
    context: PhotoGuidanceContext,
) -> PhotoGuidanceResponse:
    try:
        return await run_in_threadpool(service.analyze, image, context)
    except UnsupportedGuidanceDecisionError as exc:
        raise HTTPException(
            status_code=503,
            detail="The current guidance decision is not supported by the product contract",
        ) from exc


@router.post("/photo-guidance", response_model=PhotoGuidanceResponse)
async def photo_guidance(
    file: UploadFile = File(...),
    photo_type: PhotoType = Form(...),
    capture_slot: CaptureSlot = Form(...),
    vehicle_type: VehicleType = Form(...),
    session_id: str = Form(..., min_length=1, max_length=128),
    frame_id: int = Form(..., ge=0),
    entry_side: EntrySide | None = Form(None),
    service: Annotated[PhotoGuidanceService, Depends(get_photo_guidance_service)] = None,
) -> PhotoGuidanceResponse:
    image = await file.read()
    if not image:
        raise HTTPException(status_code=422, detail="image file must not be empty")
    context = _guidance_context(
        photo_type=photo_type,
        capture_slot=capture_slot,
        vehicle_type=vehicle_type,
        session_id=session_id,
        frame_id=frame_id,
        entry_side=entry_side,
        mode=GuidanceMode.PREVIEW,
        source=GuidanceImageSource.CAMERA_RAW,
    )
    return await _analyze_guidance(service, image, context)


@router.post("/photos", response_model=PhotoUploadResponse)
async def upload_photo(
    file: UploadFile = File(...),
    photo_type: PhotoType = Form(...),
    capture_slot: CaptureSlot = Form(...),
    vehicle_type: VehicleType = Form(...),
    session_id: str = Form(..., min_length=1, max_length=128),
    frame_id: int = Form(..., ge=0),
    entry_side: EntrySide | None = Form(None),
    guidance_service: Annotated[PhotoGuidanceService, Depends(get_photo_guidance_service)] = None,
    storage_service: Annotated[PhotoStorageService, Depends(get_photo_storage_service)] = None,
) -> PhotoUploadResponse:
    image = await file.read()
    if not image:
        raise HTTPException(status_code=422, detail="image file must not be empty")
    mime_type = file.content_type
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise HTTPException(status_code=422, detail="image content type is required")

    context = _guidance_context(
        photo_type=photo_type,
        capture_slot=capture_slot,
        vehicle_type=vehicle_type,
        session_id=session_id,
        frame_id=frame_id,
        entry_side=entry_side,
        mode=GuidanceMode.FINAL,
        # /photos also accepts gallery/file uploads, so their provenance cannot
        # truthfully be declared camera_raw without a future explicit signal.
        source=None,
    )
    guidance = await _analyze_guidance(guidance_service, image, context)
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
