# Team Status

This file records shared repository status. It is not an individual agent checkpoint or a branch diary.

## Last verified checkpoint

- Verified on: 2026-09-26
- Branch: `main`
- Commit: `911f806` (`feat(module-b): pair photo evidence by capture slot`)
- Working tree at verification: clean
- Full Python suite: **331 passed, 2 warnings, 0 failed**
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
- A Python guidance core is now available (`module_a.PhotoCoach`), including draft quality/geometry checks and manual-capture advice. It is not wired to E: the current HTTP context and acceptance schemas cannot faithfully represent its inputs and uncertainty/manual outputs. See `docs/tasks/module-a-coach.md`. Storage contracts remain unchanged; templates still require real-photo calibration.

## Module B

Completed:

- `AIAnalyzer`, `DamageModelAnalyzer`, and `AIFinding` exist.
- `CaseBuildingModuleB.analyze(case_id, photos)` is the high-level entry point and returns a Module D `Case`.
- The orchestration path is `AIFinding -> DetectionInput -> module_d.create_case()`.
- Multi-photo `CaptureSlot` evidence pairing is implemented from Module A metadata; list order is not used as provenance.
- Fixed capture slots require a BORROW/RETURN pair.
- Multiple RETURN `OTHER_DAMAGE` photos are supported as return-only evidence.
- Findings preserve their true `source_photo_id`.

Current limitation:

- The included analyzer evaluates photos individually. The evidence pairing is structurally correct, but true before/after visual comparison remains model work.

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
- In-memory Case state for the MVP.
- `module_d.api.app` remains a legacy compatibility import for the canonical app.

Open:

- The production `photo_ids -> Module B -> Module D -> Case` HTTP endpoint and its final request contract have not been implemented.
- Production Module B dependency and model-checkpoint wiring have not been added to the composition root.
- Database persistence and authentication are intentionally outside the current MVP.

## UI

Current repository state:

- `UI_backstage` calls existing Case endpoints for staff workflows.
- `UI_client` contains capture screens and prototype behavior, but still calls a prototype `/api/analyze` path rather than the canonical Module E photo routes.

Intended integration:

1. Use `POST /photo-guidance` for live capture guidance.
2. Use `POST /photos` for each accepted shutter capture and retain the returned `photo_id`.
3. Submit the completed photo ID set to the future production Case-creation endpoint.
4. Module E calls Module B in-process; Module E does not call Module B over HTTP.

## Integration blockers and gaps

- The earlier return-only evidence blocker is resolved. Module D accepts an explicitly supplied `borrow_photo_id=None`, and Module B uses it only for RETURN `OTHER_DAMAGE` evidence.
- The main missing integration contract is the production Case-creation HTTP request that receives uploaded photo IDs and invokes Module B.
- The real Module A shooting-guidance implementation must replace `StubPhotoGuidanceService` when it is available.
- `UI_client` must migrate from its prototype analysis call to the canonical Module E photo and future Case-creation flow.

## Team-level next steps

1. Design and implement the smallest production Case-creation flow in Module E: resolve stored photos, call a configured `CaseBuildingModuleB`, store the returned valid Case atomically, and return the HTTP response.
2. Replace the shooting-guidance stub when Module A's real implementation is merged.
3. Connect `UI_client` to the canonical photo and Case-creation routes.
4. Run an end-to-end demo covering capture, upload, Case creation, review, workflow, and payment.

## Differences from the previous written checkpoint

Repository inspection found three differences from the supplied starting notes:

- Module B multi-photo `CaptureSlot` pairing is already implemented.
- Module D already supports nullable borrow evidence for generic return-only detections, so that contract is no longer blocking integration.
- The confirmed full pytest checkpoint is 331 passed rather than 312 passed.

## Status-recording rule

Keep this file limited to shared module completion, integration blockers, team-level next steps, and confirmed test checkpoints. Record branch-specific implementation details in the pull request description or, when needed, under `docs/tasks/<task-name>.md`. Do not create a root `CHECKPOINT.md`.
