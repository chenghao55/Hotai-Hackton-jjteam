# Hotai iRent AI Prototype

Coding agents must read [AGENTS.md](AGENTS.md) and [docs/STATUS.md](docs/STATUS.md) before changing the repository. `AGENTS.md` contains the shared workflow and ownership rules; `docs/STATUS.md` contains the latest verified team-level status and test checkpoint.

> **Purpose of this README**
>
> This file is the architecture contract for both human teammates and coding agents.
> Before changing module boundaries, API contracts, domain models, or ownership, read this file first.
>
> **Do not "simplify" or redesign the architecture across modules unless the team explicitly agrees.**

---

## 1. Project scope

This prototype is split into six explicit responsibility areas:

```text
A  = Photo storage + photo legality / shooting guidance
B  = Vehicle-condition AI
C  = Reserved / team-owned module if present; do not absorb its work silently
D  = Case / Detection domain decisions
E  = Backend / HTTP / integration
UI = Frontend / user interaction
```

Every coding agent must first identify which responsibility area owns the requested behavior.

If a requested change belongs to another module, do not silently implement that logic in your own module.

---

## 2. Agent responsibilities and module boundaries

### Module A Agent — Photo

**Primary mission**
Build and maintain the photo subsystem.

**Owns**
- Saving accepted photos
- Reading photo bytes / metadata
- `Photo`
- `PhotoType` (`BORROW`, `RETURN`)
- `CaptureSlot` and valid `PhotoType` / `CaptureSlot` combinations
- Photo legality analysis
- Shooting-guidance analysis
- L1–L6 guidance decision logic
- PASS / reject decision for camera frames

**Current storage API**
```python
save_photo(file_bytes, photo_type, capture_slot, mime_type)
get_photo(...)
get_photo_info(...)
```

`Photo` metadata contains `photo_id`, `photo_type`, `capture_slot`, `mime_type`, and
the local `file_path`.

**Current repo state**
- Photo storage already exists.
- Python guidance core is available as `module_a.PhotoCoach`; setup and contract gaps are documented in [Module A coach integration](docs/tasks/module-a-coach.md).
- E currently uses a replaceable guidance stub.

**Guidance implementation contract**
A must expose a stable Python-level API that E can wrap with an adapter.

A should analyze one image/frame at a time and return enough information for E to map to:

```text
accepted / pass state
level
code
message
action
```

A must evaluate guidance in this priority order:

```text
L1 Lighting environment
L2 Camera stability
L3 Subject distance
L4 Centering / composition
L5 Camera height
L6 Feature angle
PASS
```

When multiple problems exist, return the first blocking guidance result by priority.

A guidance analysis must not save the image.

A should preserve existing storage APIs while adding guidance.

**Must NOT own**
- FastAPI routes
- HTTP request/response schemas
- Case creation
- Damage category / severity decisions
- Review state
- Priority
- Workflow
- Payment

**Agent completion checklist**
- Existing storage API still works
- Guidance logic is isolated from storage
- Tests cover each L1–L6 rejection class
- Tests cover PASS
- Tests cover priority ordering
- Tests verify guidance does not save photos
- Full pytest passes
- README updated if public API or structure changed

---

### Module B Agent — Vehicle-condition AI

**Primary mission**
Analyze accepted vehicle photos and produce vehicle-condition findings.

**Owns**
- AI analysis of vehicle photos
- AI findings such as:
  - category
  - severity
  - confidence
  - source photo provenance
- Converting AI findings into D-owned `DetectionInput`
- Orchestrating the call into `module_d.create_case(...)`

**Intended internal flow**

```text
accepted photos
  ↓
Module B
  ↓
AIAnalyzer / damage model
  ↓
AIFinding[]
  ↓
DetectionInput[]
  ↓
module_d.create_case(...)
  ↓
Case
```

`AIFinding.source_photo_id` is required provenance for every per-photo AI finding.
Module B forwards it to D, where it must match one of the non-`None` evidence photo IDs.

Module B accepts multiple photos and uses Module A metadata to validate their structure:

- Damage slots (`FRONT_LEFT`, `FRONT_RIGHT`, `REAR_LEFT`, `REAR_RIGHT`, and `REAR`)
  accept either a complete borrow/return pair or return-only evidence.
- A borrow-only damage slot is invalid, and duplicate borrow or return photos for the same fixed
  damage slot are invalid.
- `OTHER_DAMAGE` is return-only, may appear multiple times, and requires no borrow counterpart.
- `FUEL_PARKING_CARD`, `INTERIOR_FRONT`, and `INTERIOR_REAR` are stored photo types but are
  excluded from the damage analyzer.
- The current AI analyzes model-relevant photos independently; complete pairing is evidence
  mapping, not true before/after visual differencing.

**Important**
B owns AI interpretation, not D's domain policy.

B may produce:
- category
- severity
- confidence
- source photo provenance

B must not decide:
- `ReviewState`
- Case priority
- Case workflow
- Payment state

**Must NOT own**
- HTTP routes
- FastAPI application setup
- E schemas
- Review state
- Priority calculation
- Case workflow
- Payment workflow

**Agent completion checklist**
- B still calls D through `DetectionInput` / `create_case(...)`
- No duplicate Case-creation path is introduced
- No D policy is reimplemented in B
- Existing public B contracts remain backward-compatible unless explicitly changed
- Full pytest passes
- README updated if public API or structure changed

---

### Module C Agent — Reserved / team-owned module

**Primary mission**
Only implement responsibilities explicitly assigned to Module C by the team.

At the moment this README does not define a stable backend ownership contract for C.

**Therefore C agents must:**
- Read the task description carefully
- Avoid absorbing A/B/D/E/UI responsibilities
- Avoid changing public contracts outside C without explicit team agreement
- Use adapters/interfaces instead of cross-module rewrites
- Stop and report if the task requires redefining ownership

**Must NOT silently become**
- the photo subsystem
- the vehicle-condition AI
- the Case/domain layer
- the HTTP backend
- the UI layer

If Module C receives a formal responsibility later, document it here before large implementation work.

---

### Module D Agent — Case / Decision Domain

**Primary mission**
Own the rules of the Case/Detection domain.

**Owns**
- `Case`
- `Detection`
- `DetectionInput`
- `ReviewState`
- `CaseStatus`
- Validation of domain objects
- Initial detection assessment
- Priority calculation
- Human review
- Appeal
- Dispatch / processing workflow
- Payment state
- `create_case(...)`

Module D should remain a **pure domain layer**.

Its target architecture should not own FastAPI routes or HTTP concerns.

**Protected rule**
Do not modify D just to make an API or AI implementation easier.
Adapt E/B to D unless the domain requirement itself has changed.

**Current important flow**
```text
B
↓
DetectionInput[]
↓
D.create_case(...)
↓
Case
```

**Must NOT own**
- FastAPI app creation
- HTTP request/response models
- CORS
- multipart handling
- frontend concerns
- image storage
- image AI

**Agent completion checklist**
- Domain invariants remain enforced in D
- Review/priority/workflow/payment stay D-owned
- `DetectionInput` remains D-owned
- `source_photo_id` backward compatibility is preserved
- Return-only evidence is represented by an explicit `borrow_photo_id=None`
- Full pytest passes
- README updated if domain/public contracts changed

---

### Module E Agent — Backend / Integration

**Primary mission**
Expose stable HTTP APIs and wire A/B/D together.

**Owns**
- FastAPI application
- HTTP request/response schemas
- API routers
- CORS/configuration
- Dependency wiring
- Adapters between HTTP and module-internal APIs
- In-memory MVP Case state
- `main.py`

E must not duplicate A/B/D business logic.

**Target pattern**

```text
HTTP Request
    ↓
E route
    ↓
E adapter/service
    ↓
A / B / D
    ↓
E serializes result
    ↓
HTTP Response
```

**Current E photo routes**
```text
POST /photo-guidance
POST /photos
GET  /photos/{photo_id}
```

**Current state**
- Photo schemas complete
- Photo guidance route complete
- Photo upload route complete
- Photo retrieval route complete
- Guidance still uses a stub until A guidance is merged
- Case schemas, in-memory state, and routes are extracted into `backend/`
- `backend/main.py` is the canonical Module E composition root
- `module_d/api.py` is a legacy compatibility layer that reuses the canonical app
- `POST /cases/from-photos` accepts photo IDs, generates the Case resource ID, delegates Case building to Module B, and stores the returned Case

**Next E work**
```text
1. Replace guidance stub with Module A implementation after A is merged
2. Connect the UI client to the production Case-creation API
3. Run end-to-end demo
```

**Must NOT own**
- A's image-analysis logic
- B's vehicle-condition AI
- D's domain policy
- review-state decisions
- priority logic
- workflow rules
- payment rules

**Agent completion checklist**
- Routes contain orchestration, not domain logic
- Adapters are used for cross-module integration
- Existing public HTTP contracts remain stable unless explicitly changed
- Full pytest passes
- README progress/checkpoint updated

---

### UI Agent — Frontend / User interaction

**Primary mission**
Build the user-facing flow against E's HTTP contracts.

**Owns**
- Camera/upload UI
- Real-time guidance presentation
- Showing guidance message/action to user
- Current MVP RETURN-only photo flow
- API calling
- Loading/error states
- Case/review/payment screens if assigned by product scope
- Client-side presentation logic

**Photo guidance flow**

```text
camera frame
↓
POST /photo-guidance
↓
accepted=false
    → show guidance message
    → do not treat as transport error

accepted=true
    → enable / allow capture
```

**Final photo flow**

```text
user presses shutter
↓
POST /photos
↓
accepted=false
    → show rejection guidance
    → no photo_id

accepted=true
    → receive photo_id
    → continue workflow
```

**Important UI rule**
`accepted=false` from photo guidance/upload is a successful HTTP response, not an API failure.

UI should distinguish:
- HTTP/network/request failure
- valid guidance rejection
- valid accepted result

The canonical `UI_client` flow now uses these Module E routes directly. It uploads seven
required RETURN photos: card (`FUEL_PARKING_CARD`), front cabin (`INTERIOR_FRONT`), rear cabin
(`INTERIOR_REAR`), and four exterior corners. Card/interior IDs are stored but excluded from
`POST /cases/from-photos`; exterior IDs and optional `OTHER_DAMAGE` IDs are included. The UI
does not generate `photo_id` or `case_id`, and the result screen renders the returned Case.
`dashboard`, `/api/analyze`, analysis-demo, and camera-based appeal are not canonical paths.

**Must NOT own**
- image AI
- vehicle-condition AI
- Case priority
- review/workflow/payment business rules
- backend persistence
- Module A/B/D internal models

**Agent completion checklist**
- Uses E's public HTTP contracts
- Does not call A/B/D directly
- Handles `accepted=false` correctly
- Does not infer domain state that backend already owns
- Updates UI docs/types if E contract changes

---

## 2.1 Shared rule for all agents

Before starting any task, every A/B/C/D/E/UI agent must answer internally:

```text
1. Which module owns this behavior?
2. Which public contract am I consuming?
3. Which public contract am I changing?
4. Can an adapter solve this without changing another module?
5. Which tests must stay green?
```

If the task crosses more than one ownership boundary, make the smallest compatible change.

If more than one module's public contract must change, stop and explain the impact before silently redesigning the project.

No agent should rewrite another module merely because doing so is easier locally.

---

## 3. Current repository state

### Working / merged
- Module A photo storage
- Module A `CaptureSlot` photo metadata and return-only `OTHER_DAMAGE` validation
- Module B AI + orchestration
- Module B model-slot filtering, complete-pair compatibility, and return-only damage evidence
- Module D domain logic
- Module D nullable `borrow_photo_id` support for return-only detection evidence
- `DetectionInput`
- `create_case(...)`
- Optional `source_photo_id`
- Review / appeal / priority / workflow / payment
- Module E photo HTTP schemas (`backend/schemas/photos.py`)
- Module E `POST /photo-guidance` route with a replaceable stub service
- Module E `POST /photos` final guidance and Module A storage flow
- Module E `GET /photos/{photo_id}` binary retrieval through Module A storage
- Module E Case HTTP schemas, in-memory state, and routes
- Module E composition root at `backend.main:app`
- `UI_client` canonical RETURN capture integration through Module E photo and Case routes

Current full-suite checkpoint:

```text
349 passed
2 warnings
0 failed
```

The two warnings are third-party FastAPI/Starlette deprecation warnings and are not current functional failures.

### Temporary / transitional

`module_d/api.py` remains for legacy import compatibility only.

This is **temporary**.

It currently only:
- reuses the canonical `backend.main.app` instance
- re-exports legacy schema/state/endpoint names for import compatibility

The canonical app, development CORS configuration, HTTP schemas, state, and endpoint implementations now live under `backend/`.

The existing `POST /cases` development endpoint is also temporary.
It directly receives detections and creates a Case.
The intended internal production flow remains:

```text
photos → B → DetectionInput → D.create_case() → Case
```

---

## 4. E development plan

### E1 — Extract HTTP API from Module D

Target direction:

```text
backend/
├── main.py
├── routes/
│   ├── cases.py
│   └── photos.py
├── schemas/
│   ├── cases.py
│   └── photos.py
├── services/
│   ├── case_building.py
│   ├── photo_guidance.py
│   └── photo_storage.py
└── state/
    └── cases.py

module_a/
module_b/
module_d/
```

During E1:
- Move HTTP concerns out of `module_d`
- Preserve existing D behavior
- Do not redesign D
- Do not introduce a database
- Do not rewrite B
- Keep tests green

### E2 — Add `main.py` (complete)

`backend/main.py` is the composition root:

```text
backend/main.py
  ↓
create FastAPI app
  ↓
apply development CORS configuration
  ↓
register photo and Case routers
```

`main.py` should be a wiring layer, not a place for business logic.

The canonical ASGI import path is `backend.main:app`.

### E3 — Persistence

**Not part of MVP.**

For the demo, in-memory storage is acceptable:

```python
cases: dict[str, Case]
```

Restarting the server may clear Case state.

### E4 — Production Case creation API (complete)

`POST /cases/from-photos` accepts previously accepted photo IDs. The caller does not provide
`case_id`; Module E generates a UUID resource ID and returns it in the Case response:

```json
{
  "photo_ids": ["borrow-photo-id", "return-photo-id"]
}
```

Module E loads each photo through `PhotoStorageService`, passes ordered
`(photo_id, bytes)` values and its generated `case_id` to Module B, and stores the returned
Case only after successful analysis. The route does not create D detections or apply D policy.

Module B runtime configuration is centralized in `backend/services/case_building.py`.
`HOTAI_MODULE_B_CHECKPOINT_PATH` and `HOTAI_MODULE_B_DEVICE` override the default
`artifacts/module_b/damage_multitask.pth` path and `auto` device. The route receives a lazy
Module B provider, so tests can override it without loading the ML checkpoint.

### E5 — End-to-end demo

Target:

```text
HTTP
 ↓
E
 ↓
A / B
 ↓
D
 ↓
Case
 ↓
HTTP response
```

---

## 4.1 Cross-agent integration map

The intended end-to-end architecture is:

```text
UI
↓ HTTP
E
├─→ A   photo guidance / storage
├─→ B   vehicle-condition AI
└─→ D   Case/domain operations

B
↓
D.create_case(...)
```

Important:
- UI talks to E only.
- E may call A/B/D.
- B may call D through documented domain APIs.
- A does not call D.
- D does not call FastAPI/UI.
- C must follow whatever ownership is formally assigned later.

---

## 5. Photo HTTP contract

The photo flow has two separate operations.

### 5.1 `POST /photo-guidance`

Purpose:
- Analyze a live camera frame
- Tell the user why the current framing/photo is not acceptable
- Provide immediate shooting guidance

This endpoint:
- **does not save the photo**
- **does not create `photo_id`**
- should normally return HTTP `200` even when the frame is not acceptable

Example response:

```json
{
  "accepted": false,
  "check": {
    "level": "L2",
    "code": "BLUR",
    "message": "畫面模糊，請拿穩手機並點擊螢幕重新對焦。",
    "action": "reshoot"
  }
}
```

Successful analysis with `accepted: false` is not an HTTP error.

HTTP `4xx` is reserved for malformed/invalid requests, such as:
- missing image
- unsupported request format
- invalid required fields

### 5.2 `POST /photos`

Purpose:
- User presses the shutter
- Perform final legality/guidance validation
- Save the photo only when accepted
- Return `photo_id` for accepted photos

Multipart request fields:

```text
file
photo_type   = borrow | return
capture_slot = one of Module A's CaptureSlot values
```

Accepted example:

```json
{
  "accepted": true,
  "photo_id": "abc123",
  "check": {
    "level": "PASS",
    "code": "PASS",
    "message": "視角正確，請保持穩定並按下快門。",
    "action": "accept"
  }
}
```

Rejected example:

```json
{
  "accepted": false,
  "photo_id": null,
  "check": {
    "level": "L2",
    "code": "BLUR",
    "message": "畫面模糊，請拿穩手機並點擊螢幕重新對焦。",
    "action": "reshoot"
  }
}
```

### 5.3 `GET /photos/{photo_id}`

Returns the previously accepted/stored photo.

### 5.4 Capture slots

`CaptureSlot` is owned by Module A and is stored with every accepted photo:

```text
front_left
front_right
rear_left
rear_right
rear
interior_front
interior_rear
fuel_parking_card
other_damage
```

MVP assumption: `CaptureSlot.OTHER_DAMAGE` is return-only. It represents newly
observed damage during return and does not require a matching borrow photo.

Exterior damage slots accept either complete borrow/return evidence or a return photo alone.
When both sides are provided, their `CaptureSlot` associates findings with the evidence pair;
when only return evidence is provided, Module B passes `borrow_photo_id=None` to Module D.
The deployed AI performs independent single-photo inference and does not perform true
before/after visual differencing. Card and interior slots are not sent to the damage analyzer.

---

## 6. Shooting-guidance levels

Module A's current guidance document defines this priority order:

```text
L1  Lighting environment
L2  Camera stability
L3  Subject distance
L4  Centering / composition
L5  Camera height
L6  Feature angle
PASS
```

Suggested stable machine-readable codes:

```text
TOO_DARK
BACKLIGHT
OVEREXPOSED
BLUR
TOO_FAR
TOO_CLOSE
OFF_CENTER
ANGLE_TOO_HIGH
ANGLE_TOO_LOW
TOO_FRONT
TOO_SIDE
INTERIOR_NOT_ALIGNED
PASS
```

Suggested actions:

```text
guide
reshoot
accept
```

The exact adapter from A's model output to these HTTP fields belongs in E.
Do not force A's internal model classes to become HTTP schemas.

---

## 7. Planned photo schemas

E should define HTTP-only schemas separately from A's internal classes.

Suggested location:

```text
backend/schemas/photos.py
```

Conceptually:

```python
class PhotoCheck(BaseModel):
    level: str
    code: str
    message: str
    action: str


class PhotoGuidanceResponse(BaseModel):
    accepted: bool
    check: PhotoCheck


class PhotoUploadResponse(BaseModel):
    accepted: bool
    photo_id: str | None
    check: PhotoCheck
```

These are HTTP contracts, not AI/domain models.

---

## 8. Guardrails for coding agents

Before editing, determine which module owns the behavior.

### DO NOT
- Move review/priority/workflow/payment logic into B or E
- Make B set `ReviewState`
- Make E calculate priority
- Make A create Cases
- Put FastAPI concerns into D's domain models/logic
- Replace B → D with a new parallel Case-creation path
- Change public contracts merely to make tests pass
- Delete backward-compatible fields without checking all module users
- Introduce a database for the MVP unless explicitly requested
- Treat `module_d/api.py` as the target final architecture
- Rewrite another teammate's module as part of an unrelated task

### DO
- Preserve A/B/D responsibilities
- Keep `source_photo_id` backward-compatible
- Keep `DetectionInput` owned by D
- Let D own `create_case(...)`
- Put HTTP request/response models in E
- Use adapters between module-internal objects and HTTP schemas
- Prefer small, reviewable changes
- Run the full test suite after cross-module changes
- Report architecture-impacting changes before making them

---

## 9. Rule for cross-module changes

If a task requires changing more than one ownership boundary, stop and explain:

1. Which module contracts need to change
2. Why an adapter cannot solve it
3. Which existing tests/contracts will be affected
4. The smallest compatible migration path

Do not silently redesign the project.

---

---

## README maintenance rule

After every task, coding agents must check whether the change affects any of the following:

- module ownership
- public APIs
- request / response schemas
- data models
- cross-module flow
- project structure
- development plan
- current test checkpoint

If any of these changed, update this README in the **same task**.

Do not leave architecture-affecting or contract-affecting changes undocumented.

For implementation-only changes that do not affect architecture, contracts, module ownership, or project structure, do not rewrite unrelated README sections.

A task is **not considered complete** if it changes architecture or contracts but this README still describes the old state.

When updating this README:
1. Edit only the sections affected by the change.
2. Keep the current architecture and current repository state accurate.
3. Update the test checkpoint if the full-suite result changed.
4. Do not rewrite historical decisions unless the team explicitly changes them.
5. If the change conflicts with an existing architecture rule, stop and report the conflict before editing code.

## 10. Immediate next work

Current E sequence:

```text
1. Replace guidance stub with Module A implementation after A is merged
2. Replace the remaining staff-side prototype data when its production integration is scheduled
3. Run an end-to-end demo against the real Module E process and model checkpoint
```

Do not start database work before the MVP demo unless the team explicitly changes this plan.
