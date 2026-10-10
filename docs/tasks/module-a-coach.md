# Module A Python coach integration

The former standalone Node coach has been ported into `module_a`. The main-branch
photo storage API is unchanged. Guidance never saves photos, creates cases, or
dispatches human reviews. E supplies capture context and returns Module A's
advice. The user may press the shutter at any time; final upload reruns AI.

Development now continues on **`A_legalityAI`**. This branch incorporates main
`e69cda8` and the Python coach commit `3c417c2` through normal merges, preserving
both histories. `A_capture_coach_python` was an intermediate integration branch;
no further work on that branch is required. The old independent service is
archived under `legacy/capture-coach-v1/`. No E/UI/B/D contract is changed by this
branch consolidation. A pull request from `A_legalityAI` to `main` delivers the
Python core; E and UI wiring was completed afterward on the same branch.

## Use from Python

Install `python -m pip install -e ".[coach,test]"` in an environment with a compatible
PyTorch installation. The detector loads once on the first coached request; model paths come
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

Cabin requests include `entry_side`. Only the left-door templates are configured;
right-side requests return the existing unavailable-evidence guidance and ask the
user to shoot from the driver's-side left door. Keep the same session and increment
preview frame IDs. Submit the actual shutter photo with `mode='final'`;
it is decoded and checked again. Preview frame order is kept in memory and
expires after a gap over 60 seconds. Scope session IDs to an authenticated
user/case at E's boundary.
Inference is serialized in this MVP. E should offload the synchronous call from
the async event loop and bound its request queue.

`accepted` means AI composition/quality pass. Preview advice does not lock the
shutter. Final analysis of the submitted image returns PASS or a reshoot reason;
rejected photos are not stored. There is no timed unlock or manual-review
fallback. Right-front cabin cannot currently pass because the model lacks
front-seat classes; the coach suggests using the left door.

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

The E adapter handles context and uncertainty. These limits remain:

1. E now supplies `CaptureContext` to the coach and the UI sends slot, vehicle
   family, entry side, session, and frame identity. The checkpoint is configured
   server-side and loaded lazily.
2. `PhotoCheck` represents the coach's uncertainty and reshoot advice.
   Physical camera height and exact viewing angle remain unverified.
3. `PhotoUploadResponse` still enforces `accepted=True` iff PASS and a stored photo ID;
   rejected photos cannot have an ID. This matches the current request to
   require a fresh final PASS instead of sending uncertain photos to review.

New A public API: `CaptureContext`, `GuidanceResult`, `PhotoCoach.analyze`,
`YoloDetector`, `load_config`. This revision removes the `GuidanceResult`
manual-review fields; E's photo responses remove the corresponding optional
fields and `human_review` action. Existing storage and Case contracts remain unchanged.

## Validation and changed files

Current `A_legalityAI` guidance checkpoint (2026-09-28): the tracked Python
suite **377 passed, 1 warning, 0 failed**; the current working tree also has
six unrelated untracked comparison tests, and its full run was **383 passed**.
The archived Node suite also passes (13 API tests plus 31 geometry assertions).
The warning is the existing Starlette TestClient/httpx deprecation. Main changes
through `e69cda8` are included. The `GuidanceResult` and HTTP photo guidance
responses no longer expose timed/manual-review fields.
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
