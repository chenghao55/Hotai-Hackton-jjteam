# Module D — stage 3 (minimal API)

Pure Python dataclasses, enums, configurable policy inputs, and deterministic
domain functions for assessment, review, numeric priority calculation, payment,
and workflow, with a minimal FastAPI adapter. No persistence, frontend, or image
recognition is included.

## Run tests (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest
```

Python 3.10+ is required. Skip creating the virtual environment if it exists.
The domain code has no third-party dependencies. The API uses FastAPI and
Uvicorn; API tests use HTTPX through FastAPI TestClient.

## Run the development API (PowerShell)

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m uvicorn module_d.api:app --reload
```

Open http://127.0.0.1:8000/docs to try the two application endpoints:

- `GET /cases`: HTTP 200, a JSON array of all Cases.
- `POST /cases/{case_id}/dispatch`: no request body; calls domain
  `dispatch_case(case)` and returns the updated Case (HTTP 200). Missing IDs
  return HTTP 404. Domain ValueError returns HTTP 409 with the original message
  in the JSON `detail` field.

Try case ID `demo-001`. It starts UNASSIGNED with one automatically accepted
scratch detection and a demo score of 20. The photo references are placeholders.
Dispatching it twice produces a conflict on the second request.

The process-local dictionary resets on restart/reload and is not shared between
workers. Use one worker for this prototype. There is no persistence or API to
create Cases yet. Tests substitute isolated stores and never consume demo data.

The API uses `response_model=Case` / `list[Case]`: FastAPI's Pydantic integration
serializes the existing standard dataclasses, including nested detections,
string Enum values, and JSON null for None. No domain model conversion or
duplicate business rules are introduced. Both photo reference fields are exposed.

Development CORS allows HTTP origins localhost and 127.0.0.1 on ports 5173 and
3000, methods GET/POST, and the Content-Type header. Credentials are disabled.
These are development settings only. No other application endpoints are added.

Known pre-existing mismatch: `finish_processing()` currently rejects pending
review, but two domain tests and the older workflow description below expect it
to allow pending review. This API step does not change that rule or those tests.

## Model contract

- B supplies category, severity, and confidence for each independent finding.
  D validates confidence in [0, 1]; B's emission threshold is not D's concern.
- Detection requires an explicit review state. Use NEEDS_REVIEW as the initial
  placeholder, then call `assess_detection(detection, policy)`.
- Detection requires both `borrow_photo_id` and `return_photo_id` as nonempty
  strings. Domain operations preserve these references.
- CORRECTED stores both final reviewed values and requires a real change.
  Other states use no reviewed category/severity. Original AI values are retained.
- Dataclasses are mutable for simplicity. Constructors validate automatically;
  `validate()` explicitly rechecks a model after changes, including nested Case
  detections. Direct assignment is not intercepted. Domain operations preserve
  original AI fields and validate inputs and updated objects.
- Case `priority_score: int | None` is a stored derived maintenance priority
  score. `None` means there is currently no calculated score; `0` is a calculated
  score and is intentionally different from `None`. Scores must be exactly an
  integer from 0 through 100 inclusive; booleans and floats are rejected.
  Model validation checks type and range; `calculate_priority(case, policy)`
  recalculates and stores the score from detections.
- Payment is a nonnegative integer NTD assessed charge, independent of priority.
- `DecisionPolicy.priority_score_by_condition` maps `(category, severity)` to a
  priority score from 0 to 100. Every supported pair must be present. Mapping
  values must be exactly integers; booleans, floats, strings, and `None` are
  rejected. The review confidence threshold remains independently configurable.
- Demo scores below are prototype values only, NOT validated Hotai/iRent
  business rules.

| Category | Minor | Moderate | Severe |
|---|---|---|---|
| Scratch | 20 | 45 | 70 |
| Collision damage | 50 | 75 | 95 |
| Cleanliness | 10 | 35 | 60 |

## Implemented domain operations

Functions are available from `module_d` or `module_d.logic`. Mutating operations
update the existing objects in place and return None. `needs_review(case)` is a
read-only boolean query. Invalid inputs or actions raise ValueError with an
explanation. Proposed human review and payment updates are validated before
committing, so rejected requests do not leave partial changes.

- `assess_detection(detection, policy)`: confidence below the configured review
  threshold becomes NEEDS_REVIEW; equality or above becomes AUTO_ACCEPTED.
  There is no B-side emission threshold here. Initial assessment accepts only
  NEEDS_REVIEW/AUTO_ACCEPTED states; it cannot erase an existing human review.
- `calculate_priority(case, policy)`: stores the numeric maximum in
  `case.priority_score`. Confidence is not used in this calculation.
- `needs_review(case)`: reports whether any detection awaits review.
- `apply_review(case, detection_id, result, *, policy, reviewed_category=None,
  reviewed_severity=None, review_note=None)`: accepts CONFIRMED, REJECTED, or
  CORRECTED only. Policy is required and keyword-only so score recalculation
  never silently uses a demo policy. An unknown detection ID raises ValueError.
  Staff may revise any existing review state. CORRECTED requires both final
  values and an actual change. Confirmation/rejection clear corrected fields,
  including supplied correction arguments. Each review replaces the previous
  note (omitting it clears the note), preserves AI originals, and recalculates
  the Case score without advancing status. No review history is recorded.
- `set_payment_amount(case, amount)`: sets an independent nonnegative integer
  NTD charge before PENDING_PAYMENT/COMPLETED; booleans are rejected.

## Workflow rules

AUTO_ACCEPTED and CONFIRMED use original category/severity for priority;
CORRECTED uses reviewed values. NEEDS_REVIEW and REJECTED do not contribute.
Case priority score is the highest contributing score, or None when there are
no contributing detections. A contributing score of 0 remains 0.

The special `complete_without_action()` operation requires an UNASSIGNED or
DISPATCHED Case and all three:
no actionable detections, no NEEDS_REVIEW detections, and payment_amount == 0.
An empty Case meets those detection conditions. Pending review does not block
dispatch or starting processing. Priority changes do not advance status.

Processing finishes in PENDING_PAYMENT when payment_amount > 0, otherwise
COMPLETED. Staff confirms payment to complete a payable Case. Payment amount
updates are allowed before PENDING_PAYMENT/COMPLETED. Cases remain historical
records. No appeal fields or cross-photo deduplication are included.

| Operation | Required current status | Result |
|---|---|---|
| `dispatch_case` | UNASSIGNED | DISPATCHED |
| `start_processing` | DISPATCHED | PROCESSING |
| `finish_processing` | PROCESSING, zero charge | COMPLETED |
| `finish_processing` | PROCESSING, positive charge | PENDING_PAYMENT |
| `complete_without_action` | UNASSIGNED or DISPATCHED, shortcut conditions above | COMPLETED |
| `confirm_payment` | PENDING_PAYMENT | COMPLETED; assessed charge retained |

Other source statuses raise ValueError. Pending review does not block dispatch,
starting processing, or finishing processing. Workflow functions change only
status and preserve other fields, including the stored score and charge.

## Example

```python
from module_d import (
    Case, ConditionCategory, Detection, ReviewState, Severity,
    apply_review, assess_detection, calculate_priority, demo_policy,
    dispatch_case, finish_processing, start_processing,
)

policy = demo_policy()
detection = Detection(
    detection_id="d1", borrow_photo_id="borrow1", return_photo_id="return1",
    category=ConditionCategory.SCRATCH, severity=Severity.MINOR,
    confidence=0.65, review_state=ReviewState.NEEDS_REVIEW,
)
assess_detection(detection, policy)
case = Case("case1", [detection])
calculate_priority(case, policy)  # None: review is pending
apply_review(case, "d1", ReviewState.CONFIRMED, policy=policy)
assert case.priority_score == 20
dispatch_case(case)
start_processing(case)
finish_processing(case)  # Zero charge: COMPLETED
```

Assessment works on one Detection and cannot update an enclosing Case score.
Call `calculate_priority` after direct ingestion/assessment changes; human review
already recalculates it. Mutable dataclasses still permit callers to bypass
domain rules by assigning fields directly; integrations should use operations.
