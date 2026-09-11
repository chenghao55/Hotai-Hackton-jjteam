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
- Case priority is a stored derived value. This stage checks its type, not its
  consistency with detections; calculation belongs to the next stage.
- Payment is a nonnegative integer NTD assessed charge, independent of priority.
- The demo priority mapping is illustrative, not validated business policy.

## Agreed rules for later stages

AUTO_ACCEPTED and CONFIRMED use original category/severity for priority;
CORRECTED uses reviewed values. NEEDS_REVIEW and REJECTED do not contribute.
Case priority is the highest contributing priority, or None.

The special `complete_without_action()` operation must require all three:
no actionable detections, no NEEDS_REVIEW detections, and payment_amount == 0.
An empty Case meets those detection conditions. Pending review does not block
dispatch or starting processing. Priority changes do not advance status.

Processing finishes in PENDING_PAYMENT when payment_amount > 0, otherwise
COMPLETED. Staff confirms payment to complete a payable Case. Payment amount
updates are allowed before PENDING_PAYMENT/COMPLETED. Cases remain historical
records. No appeal fields or cross-photo deduplication are included.
