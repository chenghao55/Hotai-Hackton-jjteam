# Hotai iRent AI Prototype

> **Purpose of this README**
>
> This file is the architecture contract for both human teammates and coding agents.
> Before changing module boundaries, API contracts, domain models, or ownership, read this file first.
>
> **Do not "simplify" or redesign the architecture across modules unless the team explicitly agrees.**

---

## 1. Project scope

The prototype is split into four backend responsibilities:

```text
A = Photo storage + photo legality / shooting guidance
B = Vehicle-condition AI
D = Case / Detection domain decisions
E = Backend / HTTP / integration
```

Frontend/UI implementation is outside the scope of this architecture document.
The backend should expose stable HTTP contracts to the UI without moving UI logic into A/B/D.

---

## 2. Ownership and module boundaries

### Module A — Photo

**Owns**
- Saving accepted photos
- Reading photo bytes / metadata
- `Photo`
- `PhotoType` (`BORROW`, `RETURN`)
- Photo legality / shooting-guidance analysis once A's model is integrated

**Current storage API**
```python
save_photo(...)
get_photo(...)
get_photo_info(...)
```

**Must NOT own**
- Case creation
- Damage category / severity decisions
- Review state
- Priority
- Workflow
- Payment

---

### Module B — Vehicle-condition AI

**Owns**
- AI analysis of vehicle photos
- AI findings such as:
  - category
  - severity
  - confidence
  - source photo provenance
- Converting AI findings into D-owned `DetectionInput`
- Orchestrating the call into `module_d.create_case(...)`

**Important**
B does not own D's domain decisions.

Current intended flow:

```text
photos
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

`source_photo_id` is optional provenance for a per-photo AI finding.
When present, it must match either the borrow or return photo ID.

**Must NOT own**
- `ReviewState`
- Priority calculation
- Case workflow
- Payment workflow

---

### Module D — Case / Decision Domain

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
Its final architecture should not own FastAPI routes or HTTP concerns.

**Protected rule**
Do not modify D just to make an API or AI implementation easier.
Adapt E/B to D unless the domain requirement itself has changed.

---

### Module E — Backend / Integration

**Owns**
- FastAPI application
- HTTP request/response schemas
- API routers
- CORS/configuration
- Wiring A/B/D together
- In-memory MVP state
- `main.py`

E must not duplicate A/B/D business logic.

Example:

```text
HTTP Request
    ↓
E route
    ↓
A / B / D function
    ↓
E serializes result
    ↓
HTTP Response
```

---

## 3. Current repository state

### Working / merged
- Module A photo storage
- Module B AI + orchestration
- Module D domain logic
- `DetectionInput`
- `create_case(...)`
- Optional `source_photo_id`
- Review / appeal / priority / workflow / payment

Current merge-repair checkpoint:

```text
262 passed
2 warnings
0 failed
```

The two warnings are third-party FastAPI/Starlette deprecation warnings and are not current functional failures.

### Temporary / transitional

`module_d/api.py` still contains the development FastAPI adapter.

This is **temporary**.

It currently mixes:
- FastAPI app creation
- `/cases` routes
- in-memory `cases`
- HTTP schemas

Do not treat this file layout as the target architecture.

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
├── routes/
│   ├── cases.py
│   └── photos.py
└── schemas/
    └── photos.py

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

### E2 — Add `main.py`

`main.py` becomes the composition root:

```text
main.py
  ↓
create FastAPI app
  ↓
load config / dependencies
  ↓
register routers
  ↓
wire Module A / B / D
```

`main.py` should be a wiring layer, not a place for business logic.

### E3 — Persistence

**Not part of MVP.**

For the demo, in-memory storage is acceptable:

```python
cases: dict[str, Case]
```

Restarting the server may clear Case state.

### E4 — End-to-end demo

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
1. Define photo HTTP schemas
2. Create E photo routes
3. Add POST /photo-guidance using a stub/adaptor until A code is merged
4. Add POST /photos using final validation + A photo storage
5. Preserve GET /photos/{photo_id}
6. Extract Case routes from module_d/api.py
7. Run full pytest
8. Add main.py and register routers
9. Replace guidance stub with Module A implementation after A is merged
10. Run end-to-end demo
```

Do not start database work before the MVP demo unless the team explicitly changes this plan.
