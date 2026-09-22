# Module D — stage 3 (minimal API)

Pure Python dataclasses, enums, configurable policy inputs, and deterministic
domain functions for assessment, review, numeric priority calculation, payment,
and workflow, with a minimal FastAPI adapter. The API delegates image recognition
to Module B; persistence and frontend code are not included.

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

From the project root (the `ml` extra is required by case creation):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ml,test]"
.\.venv\Scripts\python.exe -m uvicorn module_d.api:app --reload
```

Open http://127.0.0.1:8000/docs to try the development endpoints. The adapter
has no persistence: its process-local dictionary resets on restart/reload and
is not shared between workers. Use one worker for this prototype.

| 指令格式                                                     | 用途說明                                                |
| -------------------------------------------------------- | --------------------------------------------------- |
| `GET /cases`                                             | 取得目前所有 Case                                         |
| `GET /cases/{case_id}`                                   | 取得指定 Case                                           |
| `POST /cases`                                            | 建立新的 Case，並建立其中的 Detection                          |
| `POST /cases/{case_id}/dispatch`                         | 將 Case 從 `UNASSIGNED` 派送出去                          |
| `POST /cases/{case_id}/start-processing`                 | 開始處理 Case                                           |
| `POST /cases/{case_id}/finish-processing`                | 完成處理；依付款金額進入 `COMPLETED` 或 `PENDING_PAYMENT`        |
| `POST /cases/{case_id}/complete-without-action`          | 在符合條件時直接將 Case 完成，不進行處理                             |
| `PUT /cases/{case_id}/payment`                           | 修改 Case 的付款金額                                       |
| `POST /cases/{case_id}/confirm-payment`                  | 確認付款，將 `PENDING_PAYMENT` → `COMPLETED`              |
| `POST /cases/{case_id}/detections/{detection_id}/review` | 員工審核 Detection，可 `CONFIRMED`、`REJECTED`、`CORRECTED` |
| `POST /cases/{case_id}/detections/{detection_id}/appeal` | 對 Detection 提出申訴／重新開啟審核，使其回到 `NEEDS_REVIEW`         |


`POST /cases` accepts only `case_id` and AI detection fields. It does not
accept workflow status, payment, priority, or review-state fields. Each new
detection starts as NEEDS_REVIEW, is assessed with the demo policy, and the new
Case priority is calculated. Invalid create input returns HTTP 422; duplicate
case IDs return HTTP 409. Missing Case IDs return HTTP 404. Domain ValueError
from a state-changing operation returns HTTP 409 with its message in `detail`.
Open http://127.0.0.1:8000/docs to try the application endpoints:

- `GET /cases`: HTTP 200, a JSON array of all Cases.
- `POST /cases`: accepts a caller-owned case ID plus one uploaded borrow photo
  ID and one uploaded return photo ID. Module B analyzes both images, Module D
  creates the Case, and the API returns HTTP 201.
- `POST /cases/{case_id}/dispatch`: no request body; calls domain
  `dispatch_case(case)` and returns the updated Case (HTTP 200). Missing IDs
  return HTTP 404. Domain ValueError returns HTTP 409 with the original message
  in the JSON `detail` field.

Try case ID `demo-001`. It starts UNASSIGNED with one automatically accepted
scratch detection and a demo score of 20. The photo references are placeholders.
Dispatching it twice produces a conflict on the second request.

Tests substitute isolated stores and never consume demo data.
The process-local dictionary resets on restart/reload and is not shared between
workers. Use one worker for this prototype. Tests substitute isolated stores
and never consume demo data.

Create a case after uploading both photos:

```json
{
  "case_id": "rental-001",
  "borrow_photo_id": "borrow-photo-id",
  "return_photo_id": "return-photo-id"
}
```

The deployment checkpoint defaults to
`artifacts/module_b/damage_multitask.pth`. `MODULE_B_CHECKPOINT` and
`MODULE_B_DEVICE` may override its path and device. The model is loaded lazily
once per process. Duplicate case IDs return 409, missing photos return 404,
incorrect photo types or undecodable images return 422, and an unavailable
model or failed inference returns 503 without storing a partial Case.

The API uses `response_model=Case` / `list[Case]`: FastAPI's Pydantic integration
serializes the existing standard dataclasses, including nested detections,
string Enum values, and JSON null for None. No domain model conversion or
duplicate business rules are introduced. Both photo references and the actual
`source_photo_id` analyzed for each detection are exposed.

Development CORS allows HTTP origins localhost and 127.0.0.1 on ports 5173 and
3000, methods GET/POST/PUT, and the Content-Type header. Credentials are
disabled. These are development settings only.

## Model contract

- B supplies source photo ID, category, severity, and confidence for each
  independent finding.
  D validates confidence in [0, 1]; B's emission threshold is not D's concern.
- Detection requires an explicit review state. Use NEEDS_REVIEW as the initial
  placeholder, then call `assess_detection(detection, policy)`.
- Detection requires both `borrow_photo_id` and `return_photo_id` as nonempty
  strings. `source_photo_id` must equal one of them. Domain operations preserve
  all three references.
- CORRECTED stores both final reviewed values and requires a real change.
  NEEDS_REVIEW may retain both previous corrected values after appeal; they must
  be valid enums and differ from the AI result in at least one field. Partial
  pairs are invalid. Other states require both fields to be None. AI values are retained.
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

NEEDS_REVIEW, AUTO_ACCEPTED, and CONFIRMED use original AI category/severity
for priority. CORRECTED uses reviewed values. Only REJECTED does not contribute.
Pending review contributes so staff can prioritize the review queue, even when
previous corrected values are preserved after appeal.
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
records. No appeal model, review history, or cross-photo deduplication is included.

| Operation | Required current status | Result |
|---|---|---|
| `dispatch_case` | UNASSIGNED | DISPATCHED |
| `start_processing` | DISPATCHED | PROCESSING |
| `finish_processing` | PROCESSING, no pending review, zero charge | COMPLETED |
| `finish_processing` | PROCESSING, no pending review, positive charge | PENDING_PAYMENT |
| `complete_without_action` | UNASSIGNED or DISPATCHED, shortcut conditions above | COMPLETED |
| `confirm_payment` | PENDING_PAYMENT | COMPLETED; assessed charge retained |

Other source statuses raise ValueError. Pending review does not block dispatch,
or starting processing. Finishing processing requires no NEEDS_REVIEW detections;
otherwise ValueError is raised with all Case state preserved. Workflow functions change only
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
    source_photo_id="return1",
    category=ConditionCategory.SCRATCH, severity=Severity.MINOR,
    confidence=0.65, review_state=ReviewState.NEEDS_REVIEW,
)
assess_detection(detection, policy)
case = Case("case1", [detection])
calculate_priority(case, policy)  # 20: pending review uses the original AI finding
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


## Appealing a detection

`appeal_detection(case, detection_id, *, policy)` reopens a detection as
NEEDS_REVIEW, preserving previous reviewed category/severity and note for context.
Original AI fields and photo references remain unchanged. The Case score is
recalculated using original AI values for the appealed detection. Unknown IDs
raise ValueError without changes. Appeals do not change Case status or payment.
No source review-state restriction is imposed; repeating an appeal is allowed.

The next `apply_review` replaces the note (omitting it clears it), clears reviewed
values for CONFIRMED/REJECTED, or replaces them for CORRECTED. No history is stored.
Initial assessment rejects pending findings containing preserved corrected values
before mutation; these require human review. Without history fields, an appealed
CONFIRMED/REJECTED finding is indistinguishable from other pending findings to
initial assessment, so callers should use assessment only for initial AI results.
