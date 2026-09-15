# Module D — stage 2

Pure Python dataclasses, enums, configurable policy inputs, and deterministic
domain functions for assessment, review, numeric priority calculation, payment,
and workflow. No API, persistence, frontend, or image recognition is included.

## Run tests (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest
```

Python 3.10+ is required. Skip creating the virtual environment if it exists.
Runtime code has no third-party dependencies.

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
