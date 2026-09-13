# Module D — stage 1

Pure Python dataclasses, enums, and configurable policy inputs. No image
recognition, review operations, priority calculation, or workflow functions yet.

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
- Detection requires an explicit review state. Policy-based initial assessment
  will be implemented in the next stage.
- CORRECTED stores both final reviewed values and requires a real change.
  Other states use no reviewed category/severity. Original AI values are retained.
- Dataclasses are mutable for simplicity. Constructors validate automatically;
  `validate()` explicitly rechecks a model after changes, including nested Case
  detections. Direct assignment is not intercepted. Future domain operations
  should preserve original AI fields and validate updated objects.
- Case `priority_score: int | None` is a stored derived maintenance priority
  score. `None` means there is currently no calculated score; `0` is a calculated
  score and is intentionally different from `None`. Scores must be exactly an
  integer from 0 through 100 inclusive; booleans and floats are rejected.
  This stage validates the type and range, not consistency with detections;
  calculation belongs to the next stage.
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

## Agreed rules for later stages

AUTO_ACCEPTED and CONFIRMED use original category/severity for priority;
CORRECTED uses reviewed values. NEEDS_REVIEW and REJECTED do not contribute.
Case priority score is the highest contributing score, or None when there are
no contributing detections. A contributing score of 0 remains 0.

The special `complete_without_action()` operation must require all three:
no actionable detections, no NEEDS_REVIEW detections, and payment_amount == 0.
An empty Case meets those detection conditions. Pending review does not block
dispatch or starting processing. Priority changes do not advance status.

Processing finishes in PENDING_PAYMENT when payment_amount > 0, otherwise
COMPLETED. Staff confirms payment to complete a payable Case. Payment amount
updates are allowed before PENDING_PAYMENT/COMPLETED. Cases remain historical
records. No appeal fields or cross-photo deduplication are included.
