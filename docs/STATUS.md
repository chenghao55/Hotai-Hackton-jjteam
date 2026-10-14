# Team Status

This file records shared repository status. It is not an individual agent checkpoint or a branch diary.

## Latest recorded verification

- Verified on: 2026-10-12
- Verified against: the Module A mirror-ready configuration, interior presence rules, sedan demo pilots, and Module E integration current on that date; this checkpoint predates later model and template changes
- Full Python suite: **474 passed, 1 warning, 0 failed**
- Command: `python -m pytest -q`
- The warning is a third-party Starlette TestClient/httpx deprecation in the validation environment.
- A later documentation-cleanup run recorded `UI_client` **33 passed** with a successful production build and `UI_backstage` **58 passed** with a successful production build.

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

- Cabin templates cover driver-side left-door front and rear shots only; right-side requests guide the user to the left door.
- Front templates require a near-side `mirror` detection when the loaded model supports that class. The supplied eight-class checkpoint is installed as `artifacts/module_a/best.pt`; sedan front mirrors and both sedan rear templates were calibrated on demo detections. All four front and four rear demo photos return `PASS`. See `docs/coach-front-templates.svg` and `docs/coach-rear-templates.svg`. SUV calibration remains open. The model misses the required class in one demo front-cabin and both rear-cabin photos. Cabin front/rear composition passes on steering-wheel/rear-seat-bench detection respectively, after image quality checks.

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

- The exterior coach uses the approved close-up layout (image-relative feature positions, one near wheel, plate, and front headlight where applicable). Body cropping and detected features touching the image edge are allowed; there is no body-height minimum. Body width, maximum size, required detections, geometry, and ambiguity checks remain. Doors and taillights are not automatically verified. Real-photo calibration and front/rear disambiguation remain open. No public Python or HTTP contract changed.
- A 2026-10-12 pilot adjusted the sedan front-left template from one real portrait photo; that sample passes the actual model in final mode, while its paired return photo still lacks required detections. A second pilot calibrated sedan front-right from two portrait demo photos; both pass the actual model in final mode, while the two demo rear-left photos remain ambiguous. Independent validation and other slots remain open. These demo samples do not establish a real-photo pass rate.
- Left-front/rear-right and right-front/rear-left can share plate and near-wheel geometry. The current detector has no taillight class and sometimes identifies rear lamps as headlights, so the template matcher is not a reliable front-versus-rear classifier. An independently validated front/rear cue is still needed; ambiguity rejection remains enabled.
- The Python guidance core (`module_a.PhotoCoach`) is wired through Module E. The shutter stays available; final upload reruns AI on the submitted image and returns accept or reshoot. The 20-second unlock/manual-review fallback is removed. Calibration status no longer produces a guidance code or blocks uploads; quality and geometry checks still apply. Real-photo validation remains open.
- Module A has a callable offline borrow/return comparison pipeline for two already stored exterior photos. It returns alignment diagnostics, a comparison-area mask, candidate heatmap regions and a failure reason. An automated local batch smoke runner exists; there is still no trusted rental-pair lookup, annotated real-pair calibration, E route, B consumption, or C/UI reshoot integration. The normal final-upload flow is unchanged. The initial-contest scope defers accuracy calibration and human annotation to the final round.
- A local evaluation script inventories filename-based borrow/return candidates from explicitly selected photo folders. Review outputs remain local and Git-ignored; filename matches are not verified rental evidence.

The existing HTTP `TEMPLATE_NOT_CALIBRATED` enum value remains for compatibility, but the current Module A coach no longer emits it. A successful coach result now says `照片可提交。`.

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
- The active `UI_backstage` queue uses the real Case endpoints for dispatch, review, appeal, workflow, payment, and no-action completion. Vehicle and gallery decorations remain placeholders because the Case API does not yet expose rental/customer metadata or a photo-gallery contract.
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
- Ten templates are enabled for the six coached slots (8 exterior vehicle-specific templates and 2 shared driver-side cabin templates). Demo calibration exists, but broader field validation, SUV calibration, and reliable front/rear disambiguation remain open.
- Card, other-damage, and legacy rear slots receive image-format validation only. Final files use `uploaded_photo` provenance rather than claiming a live camera origin.
- The staff UI uses real workflow endpoints, but its vehicle/gallery decorations remain placeholders until the Case API provides rental/customer and photo-gallery data.

## Team-level next steps

1. Expand Module A field validation, including SUV templates, front/rear disambiguation, and the deployed UI against the real model service.
2. Replace staff-side vehicle/gallery placeholders when the Case API gains rental/customer and photo-gallery data, without moving Module D rules into the UI.
3. Run an end-to-end demo covering capture, upload, Case creation, review, workflow, and payment.

## Differences from the previous written checkpoint

Repository inspection found three differences from the supplied starting notes:

- Module B now follows the deployed single-image model: return-only exterior evidence is valid,
  while card and interior photos are filtered out before inference.
- Module D already supports nullable borrow evidence for generic return-only detections, so that contract is no longer blocking integration.
- The latest recorded all-green Python checkpoint is 474 passed (2026-10-12). It includes 53 guidance/close-up tests, 10 comparison tests, 1 batch-runner test, and 2 candidate-manifest tests, but predates later model and template changes.

## Status-recording rule

Keep this file limited to shared module completion, integration blockers, team-level next steps, and confirmed test checkpoints. Record branch-specific implementation details in the pull request description or, when needed, under `docs/tasks/<task-name>.md`. Do not create a root `CHECKPOINT.md`.
