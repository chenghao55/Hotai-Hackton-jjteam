# Module A Python coach integration

The former standalone Node coach has been ported into `module_a`. The main-branch
photo storage API is unchanged. Guidance never saves photos, creates cases, or
dispatches human reviews. Existing E routes still use their stub until their
context and decision contracts are extended.

Development now continues on **`A_legalityAI`**. This branch incorporates main
`e69cda8` and the Python coach commit `3c417c2` through normal merges, preserving
both histories. `A_capture_coach_python` was an intermediate integration branch;
no further work on that branch is required. The old independent service is
archived under `legacy/capture-coach-v1/`. No E/UI/B/D contract is changed by this
branch consolidation. A pull request from `A_legalityAI` to `main` delivers the
Python core; HTTP wiring remains the separately documented next step below.

## Use from Python

Install `python -m pip install -e ".[coach,test]"` in an environment with a compatible
PyTorch installation. The detector loads once at server startup; model paths come
from server configuration, never an uploaded request. The checkpoint is not committed.

```python
from pathlib import Path
from module_a import (CaptureContext, CaptureSlot, PhotoType, PhotoCoach,
                      YoloDetector, load_config)

config = load_config()
coach = PhotoCoach(YoloDetector('/trusted/path/best.pt', config), config=config)
context = CaptureContext(
    photo_type=PhotoType.BORROW,
    capture_slot=CaptureSlot.FRONT_LEFT,
    vehicle_type='sedan',
    session_id='server-scoped-capture-session',
    frame_id=1,
)
result = coach.analyze(Path('/path/frame.jpg').read_bytes(), context)
```

Use `entry_side='left'` or `'right'` for cabin slots. Keep the same session and
increment preview frame IDs. Submit the actual shutter photo with `mode='final'`;
it is decoded and checked again. Session timers are in memory, reset on process
restart or a preview gap over 60 seconds, and require a single coach instance (or
session affinity). Scope session IDs to an authenticated user/case at E's boundary.
Inference is serialized in this MVP. E should offload the synchronous call from
the async event loop and bound its request queue.

`accepted` means AI composition/quality pass. `can_capture=True` and
`review_required=True` mean manual submission is available, while `accepted`
remains false. `code` retains the reason. It does not mean a review task was created.
The timeout defaults to 20 seconds; dark, blurry, missing exterior subject,
cropped body and confidently wrong-slot images cannot bypass their checks.
Right-front cabin is an explicit manual-only exception: the model lacks front
seat classes and a steering wheel may be obscured.

The six service IDs remain car=0, headlight=1, license_plate=2, rear_seat_bench=3,
steering_wheel=4, wheel=5. The old seven-class checkpoint is remapped by validated
class names; a checkpoint already using the six expected classes is also accepted.
Templates remain uncalibrated: real automatic PASS is disabled. Synthetic test
fixtures exercise calibrated behavior without claiming measured field accuracy.

## Main-branch mappings and remaining contracts

| Standalone field | Main Python field |
|---|---|
| `capture_phase=checkout` | `PhotoType.BORROW` |
| `capture_phase=return` | `PhotoType.RETURN` |
| `exterior_front_left/right` | `CaptureSlot.FRONT_LEFT/FRONT_RIGHT` |
| `exterior_rear_left/right` | `CaptureSlot.REAR_LEFT/REAR_RIGHT` |
| `interior_front/rear` | `CaptureSlot.INTERIOR_FRONT/INTERIOR_REAR` |

`REAR`, `FUEL_PARKING_CARD`, and `OTHER_DAMAGE` return `UNSUPPORTED_SLOT`.
The stored Photo, PhotoType, CaptureSlot and save/get APIs are unchanged.
L1 light, L2 single-frame sharpness, L3 distance and L4 centering are evaluated.
Box feature geometry is reported at L6; L5 physical camera height is explicitly
`not_applicable`. L6 is template conformity, not proof of a 45-degree angle.
Single-frame sharpness is not an IMU or temporal camera-stability measurement.

An E-only adapter cannot faithfully connect the current public HTTP contract:

1. `/photo-guidance` receives only `file`; its service receives only image bytes.
   Both preview and final analysis need capture slot, vehicle family, entry side,
   session and frame identity. `/photos` has slot/type but does not pass them to
   guidance yet. E must explicitly supply `CaptureContext`, without guessing.
2. `PhotoCheck` enums cannot represent missing subjects, unknown geometry,
   uncalibrated templates, unsupported slots or manual review. Do not translate
   these to a false PASS or fabricate height/direction advice.
3. `PhotoUploadResponse` enforces `accepted=True` iff PASS and a stored photo ID;
   rejected photos cannot have an ID. Manual-pending evidence therefore needs a
   backward-compatible explicit submission/review state (and photo ID handling)
   agreed with E/UI/D. A emits advice only; D owns review policy and dispatch.

Smallest proposed extension: add explicit capture context to E's guidance call;
add machine-readable uncertainty/manual states and separate AI acceptance from
permission to store pending evidence. Keep existing PASS/reshoot responses valid.
Affected tests/callers: `tests/backend/test_photo_schemas.py`,
`test_photo_guidance_route.py`, `test_photo_upload_route.py`, the E guidance
provider, and `UI_client` shutter/upload flow. These contracts are not changed here.

New A public API: `CaptureContext`, `GuidanceResult`, `PhotoCoach.analyze`,
`YoloDetector`, `load_config`. No existing public contract is changed.

## Validation and changed files

Current consolidated `A_legalityAI` checkpoint (2026-09-28): focused Module A
tests **40 passed**; full Python suite **375 passed, 1 warning, 0 failed**.
The archived Node suite also passes (13 API tests plus 31 geometry assertions).
The warning is the existing Starlette TestClient/httpx deprecation. Main changes
through `e69cda8` are included. No existing Python storage or HTTP contract changed.
The old tracked `__pycache__/model.cpython-313.pyc` was removed from tracking;
model weights, environments, runtime output and untracked local notes are excluded.

Previous integration checkpoint on `A_capture_coach_python`, based on main `96a776a`:
`python -m pytest -q` → **357 passed, 1 warning, 0 failed**. The warning is a
third-party Starlette TestClient/httpx deprecation in this environment. The 26
new tests cover draft versus calibrated decisions, first-frame PASS, timeout,
final revalidation, stale sessions, all 12 templates, missing features and
unchanged storage. These tests use synthetic photos and detections, not an
accuracy benchmark.

Local `best.pt` also loaded successfully through `YoloDetector`; CPU inference
on a blank synthetic image completed with zero detections and the expected raw
0/2–6 to service 0–5 mapping. This is a loading/inference smoke check only.

Changed files: `module_a/__init__.py`, `module_a/guidance.py`,
`module_a/coach_geometry.py`, `module_a/coach_image.py`,
`module_a/capture_templates.json`, `tests/module_a/test_guidance.py`,
`pyproject.toml`, `README.md`, `docs/STATUS.md`, and this document.
