# Team Status

This file records shared repository status. It is not an individual agent checkpoint or a branch diary.

## Last verified checkpoint

- Verified on: 2026-09-28
- Verified against: current `main` worktree
- Full Python suite: **349 passed, 2 warnings, 0 failed**
- Command: `python -m pytest -q`
- The two warnings are existing FastAPI/Starlette dependency deprecation warnings.

## Current cross-module flow

The intended backend flow is:

```text
UI
  -> Module E HTTP routes and adapters
  -> Module A photo storage / metadata and Module B case building
  -> Module D case domain
```

Module A, Module B, and Module D communicate through Python calls in the same backend process. Module E owns the HTTP boundary. Module E must not duplicate Module D rules.

## Module A

Completed:

- Local filesystem photo storage and lookup.
- `PhotoType.BORROW` and `PhotoType.RETURN`.
- `CaptureSlot` values:
  - `FRONT_LEFT`
  - `FRONT_RIGHT`
  - `REAR_LEFT`
  - `REAR_RIGHT`
  - `REAR`
  - `INTERIOR_FRONT`
  - `INTERIOR_REAR`
  - `FUEL_PARKING_CARD`
  - `OTHER_DAMAGE`
- Photo metadata contains `photo_id`, `photo_type`, `capture_slot`, `mime_type`, and `file_path`.
- `OTHER_DAMAGE` is validated as RETURN-only.

Open:

- Real shooting-guidance AI has not been integrated. Module E currently uses a stub guidance service.

## Module B

Completed:

- `AIAnalyzer`, `DamageModelAnalyzer`, and `AIFinding` exist.
- `CaseBuildingModuleB.analyze(case_id, photos)` is the high-level entry point and returns a Module D `Case`.
- The orchestration path is `AIFinding -> DetectionInput -> module_d.create_case()`.
- Multi-photo evidence mapping is implemented from Module A metadata; list order is not used as provenance.
- Exterior damage slots accept a complete BORROW/RETURN pair or RETURN-only evidence.
- BORROW-only fixed damage slots and duplicate sides remain invalid.
- Multiple RETURN `OTHER_DAMAGE` photos are supported as return-only evidence.
- `FUEL_PARKING_CARD`, `INTERIOR_FRONT`, and `INTERIOR_REAR` are excluded from damage-model input.
- Findings preserve their true `source_photo_id`.

Current limitation:

- The included analyzer evaluates model-relevant photos individually. Complete-pair evidence
  mapping is structurally correct, but true before/after visual comparison remains model work.

## Module C

Module C has no stable responsibility or public contract recorded in the current repository. The team must define it explicitly before implementation. It must not absorb another module's ownership by default.

## Module D

Completed:

- `Case`, `Detection`, and `DetectionInput` domain models.
- Case creation through `create_case()`.
- Detection assessment, human review, and appeal.
- Priority calculation.
- Workflow and payment operations.
- Generic return-only evidence support:
  - `DetectionInput.borrow_photo_id: str | None`
  - `Detection.borrow_photo_id: str | None`
  - callers must still pass `borrow_photo_id` explicitly;
  - `return_photo_id` remains a required non-empty string;
  - `source_photo_id`, when present, must match one of the non-`None` evidence photo IDs.

Module D does not import Module A, `PhotoType`, or `CaptureSlot`. Module B decides when return-only evidence is valid.

## Module E

Completed:

- `backend.main:app` is the canonical FastAPI application.
- Photo HTTP schemas and services.
- `POST /photo-guidance`.
- `POST /photos`.
- `GET /photos/{photo_id}`.
- Case HTTP schemas and routes, including the existing review, appeal, workflow, and payment endpoints.
- `POST /cases/from-photos` accepts accepted `photo_ids`; Module E generates the UUID `case_id`, loads bytes through the storage adapter, calls injected Module B, and stores the Case only after successful analysis.
- Module B checkpoint and device configuration are centralized in `backend/services/case_building.py`; tests override the lazy provider and do not load ML.
- In-memory Case state for the MVP.
- `module_d.api.app` remains a legacy compatibility import for the canonical app.

Open:

- Database persistence and authentication are intentionally outside the current MVP.

## UI

Current repository state:

- `UI_backstage` calls existing Case endpoints for staff workflows.
- The active `UI_backstage` queue loads real Cases from Module E and uses real endpoints for dispatch, confirm/reject review, appeal, workflow transitions, payment confirmation, and no-action completion. It safely displays Cases with no detections and does not fall back to demo Case state.
- `UI_client` uses the canonical Module E routes for the RETURN-only capture flow.
- Live guidance uses `POST /photo-guidance`; final captures use `POST /photos`; Case creation uses `POST /cases/from-photos`.
- Seven required photos are uploaded. Card/front-cabin/rear-cabin IDs are stored but excluded from Case evidence; four exterior IDs and optional `OTHER_DAMAGE` IDs are included.
- Module E supplies every `photo_id` and `case_id`. The result page renders only the returned Module D Case fields.
- `dashboard`, `/api/analyze`, analysis-demo, legacy capture, and camera-based appeal are removed from the canonical flow.

Implemented integration:

1. Use `POST /photo-guidance` for live capture guidance.
2. Use `POST /photos` for each accepted shutter capture and retain the returned `photo_id`.
3. Submit the completed photo ID set to `POST /cases/from-photos`.
4. Module E calls Module B in-process; Module E does not call Module B over HTTP.

## Integration blockers and gaps

- Return-only damage evidence is supported end to end. Module D accepts an explicitly supplied
  `borrow_photo_id=None`, and Module B uses it for RETURN exterior/damage photos without
  fabricating borrow evidence.
- The real Module A shooting-guidance implementation must replace `StubPhotoGuidanceService` when it is available.
- `UI_backstage` corrected review remains unsupported until the UI supplies `reviewed_category` and `reviewed_severity`; payment amount editing remains unsupported until a UI is added for the existing payment endpoint. The displayed vehicle/gallery decorations are placeholders because Case responses do not contain rental/customer metadata or a photo-gallery contract.

## Team-level next steps

1. Replace the shooting-guidance stub when Module A's real implementation is merged.
2. Add corrected-review and payment-amount inputs to the staff UI when the MVP needs those actions, without moving Module D rules into the UI.
3. Run an end-to-end demo covering capture, upload, Case creation, review, workflow, and payment.

## Differences from the previous written checkpoint

Repository inspection found three differences from the supplied starting notes:

- Module B now follows the deployed single-image model: return-only exterior evidence is valid,
  while card and interior photos are filtered out before inference.
- Module D already supports nullable borrow evidence for generic return-only detections, so that contract is no longer blocking integration.
- The confirmed full pytest checkpoint is now 349 passed.

## Status-recording rule

Keep this file limited to shared module completion, integration blockers, team-level next steps, and confirmed test checkpoints. Record branch-specific implementation details in the pull request description or, when needed, under `docs/tasks/<task-name>.md`. Do not create a root `CHECKPOINT.md`.
