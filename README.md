# Hotai modules

## Module B — single-photo damage assessment

Module B uses a `512×512` LR-ASPP MobileNetV3-Large semantic segmentation model
to detect `scratch` and `collision_damage`. `no_detected_damage` is an
image-level state derived when neither detection passes its saved probability
and minimum-area gates; it is not a trained damage category. One image can have
both damage detections.

Pillow applies EXIF orientation, converts JPG/JPEG/JFIF/PNG images to RGB in
memory, then preserves the complete frame while resizing and padding. Source
images are never rewritten. Severity is a fixed mapping: scratch is moderate
and collision damage is severe. Every assessment remains `needs_review` and
`experimental_review_only`.

Prepare the licensed HITL polygon manifest and train:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ml,test]"
.\.venv\Scripts\python.exe -m module_b.prepare_condition_data `
  --hitl-root "<extracted HITL dataset root>" `
  --hitl-version "download-YYYY-MM-DD" `
  --output data/condition_manifest.hitl-only.json

.\.venv\Scripts\python.exe -m module_b.train_damage_segmentation `
  --manifest data/condition_manifest.hitl-only.json `
  --output-dir artifacts/module_b `
  --device auto
```

Recommended image-level API:

```python
from module_b import load_damage_segmentation_model, predict_damage_assessment

bundle = load_damage_segmentation_model(
    "artifacts/module_b/damage_multitask.pth",
    device="auto",
)
assessment = predict_damage_assessment(bundle, "example.jfif", photo_id="photo-001")
print(assessment.to_dict())
```

`damage_state` is `damage_detected` when `detections` is nonempty; otherwise it
is `no_detected_damage`. The parallel field is deliberately named
`claim_candidate`, not a final claim decision:

| Damage state | Candidate label | Module D input |
|---|---|---|
| `damage_detected` | `claim_candidate` | one or more detections |
| `no_detected_damage` | `no_claim_candidate` | empty detections |

`predict_damage_conditions()` remains available when only the low-level list of
damage findings is needed. Confidence is a model score, not a calibrated damage
or claim probability. Full architecture, training results, and limitations are
documented in [`module_b/ARCHITECTURE.md`](module_b/ARCHITECTURE.md) and
[`module_b/FINE_TUNING_CONDITIONS.md`](module_b/FINE_TUNING_CONDITIONS.md).

### Backend integration

The FastAPI backend accepts uploaded borrow/return photos and exposes
`POST /cases`. Module B analyzes both photos independently, records each
finding's `source_photo_id`, and passes category, fixed severity, and confidence
to Module D. Module D owns review-state and priority decisions. This integration
does not compare before/after pixels and does not determine whether a visible
condition was caused during the rental.

Evaluate the simplified claim-candidate rule against the private Hotai folder
labels without tuning on them:

```powershell
.\.venv\Scripts\python.exe -m module_b.evaluate_hotai_claim_proxy `
  --data-root "<folder containing 沒有進行索賠 and 進行索賠資料>" `
  --checkpoint artifacts/module_b/damage_segmenter.pth
```

This measures agreement with the claim/no-claim folders, not scratch/collision
category accuracy, because those photos do not have category annotations.

### Current Hotai proxy result

The existing checkpoint was evaluated once on all 293 private Hotai images
without changing its thresholds. It predicted `damage_detected` for every image:

| Unit | Accuracy | Claim recall | No-claim specificity | False positives | False negatives |
|---|---:|---:|---:|---:|---:|
| Image (293) | 18.1% | 100% | 0% | 240 | 0 |
| Vehicle group (58) | 48.3% | 100% | 0% | 30 | 0 |

It emitted `collision_damage` on 293 images and `scratch` on 284; no image was
`no_detected_damage`. This is an unusable all-positive result, consistent with
domain shift and overly permissive external-data gates. The checkpoint must not
be used for automatic claim decisions. The complete local report is generated
at `artifacts/module_b/hotai_claim_proxy_metrics.json`.

A grouped single-photo calibration pipeline is implemented in
`module_b.train_damage_calibrator`. It extracts 8-connected component features,
keeps the segmenter frozen, performs five-fold out-of-fold logistic calibration,
and selects the lowest-false-positive threshold subject to at least 95% recall.
On the current data, no qualifying threshold improved the 100% baseline
false-positive rate. Training therefore fails closed with
`status=quality_gate_failed` and does not create `damage_calibrated.pth`; its
diagnostic report is `artifacts/module_b/damage_calibration_metrics.json`.

### Minimal local annotation

Because claim/no-claim is not a reliable per-photo visible-damage label, launch
the localhost-only annotation UI and label the fixed 100-image queue:

```powershell
.\.venv\Scripts\python.exe -m module_b.annotate_hotai `
  --data-root "<folder containing 沒有進行索賠 and 進行索賠資料>" `
  --count 100 `
  --port 8765
```

Open `http://127.0.0.1:8765/`. For every image choose visible damage
`yes/no/uncertain`; when yes, select `scratch`, `collision_damage`, both, or
`uncertain_category`. Keyboard shortcuts 1–5 and Enter are available. The
deterministic queue and annotations are saved only under `data/` and are ignored
by Git. Restarting the same command resumes completed work.

### Visible-damage gate result

The completed annotation set contains 99 usable images (23 visible-damage,
76 no-visible-damage) plus one excluded `uncertain` image. A MobileNetV3-Large
single-photo gate was evaluated with vehicle-group-separated five-fold
cross-validation and a locked 21-image test set. The 90% minimum OOF-recall
setting produced the following result:

| Split | Recall | Specificity | False positives | False negatives | Accuracy |
|---|---:|---:|---:|---:|---:|
| OOF development (78) | 94.4% | 21.7% | 47 / 60 | 1 / 18 | 38.5% |
| Locked test (21) | 100% | 0% | 16 / 16 | 0 / 5 | 23.8% |

The stricter 95% setting kept zero OOF false negatives but increased the OOF
false-positive rate to 85%; the locked-test result was still all-positive. The
quality gate therefore failed closed. No `damage_with_gate.pth` was created,
and `damage_segmenter.pth` remains experimental/review-only. Exact metrics are
written to `artifacts/module_b/visible_damage_gate_metrics.json`.

Run the reproducible gate experiment with:

```powershell
.\.venv\Scripts\python.exe -m module_b.train_visible_damage_gate `
  --queue data\hotai_annotation_queue.json `
  --annotations data\hotai_annotations.json `
  --base-checkpoint artifacts\module_b\damage_segmenter.pth `
  --output-dir artifacts\module_b `
  --device auto `
  --minimum-oof-recall 0.90
```

This command only publishes the combined checkpoint when both OOF and locked
test reject at least one no-damage image. A failed run saves diagnostics but
does not expose a model as a usable artifact.

### HITL + Hotai multitask model

The current experimental model shares the LR-ASPP MobileNetV3-Large backbone
between two separately supervised tasks. HITL polygons train the
`scratch`/`collision_damage` segmentation head; the 99 usable manually labelled
Hotai photos train an image-level visible-damage gate. The labels are never
treated as interchangeable. Hotai training batches use balanced resampling and
an unweighted binary loss, while validation and locked test retain their
original distributions and vehicle-group isolation.

Locked Hotai performance (21 photos):

| Metric | Result |
|---|---:|
| Visible-damage recall | 100% (5 / 5) |
| No-visible-damage specificity | 68.8% (11 / 16) |
| False-positive rate | 31.2% (5 / 16) |
| Accuracy | 76.2% (16 / 21) |
| Balanced accuracy | 84.4% |

The checkpoint passed the configured experimental gate of recall >= 80% and
specificity >= 50% and is saved as `artifacts/module_b/damage_multitask.pth`.
The test contains only five positive images, so this result is not yet a stable
production estimate and the checkpoint remains `experimental_review_only`.

Train it with:

```powershell
.\.venv\Scripts\python.exe -m module_b.train_multitask_damage `
  --manifest data\condition_manifest.hitl-only.json `
  --queue data\hotai_annotation_queue.json `
  --annotations data\hotai_annotations.json `
  --base-checkpoint artifacts\module_b\damage_segmenter.pth `
  --output-dir artifacts\module_b `
  --device auto `
  --minimum-validation-recall 0.75 `
  --minimum-locked-recall 0.80 `
  --minimum-locked-specificity 0.50
```

Inference uses the existing API:

```python
from module_b import load_damage_segmentation_model, predict_damage_assessment

bundle = load_damage_segmentation_model(
    "artifacts/module_b/damage_multitask.pth",
    device="auto",
)
assessment = predict_damage_assessment(bundle, "example.jfif", "photo-001")
print(assessment.to_dict())
```

The gate first rejects likely no-damage photos. Photos that pass are sent to
the segmentation head and may emit `scratch`, `collision_damage`, or both.
`claim_candidate` remains a visible-damage proxy, not a final insurance claim
decision.

### Deprecated claim v1

The old `load_claim_model()` and `predict_claim()` API and `claim_model.pth`
checkpoint remain available for compatibility, but they are deprecated and do
not participate in the v2 decision path. The old private claim dataset is not
used by condition training.

## Module D — stage 2

Pure Python dataclasses, enums, configurable policy inputs, and deterministic
domain functions for assessment, review, numeric priority calculation, payment,
and workflow. The development API delegates image recognition to Module B;
persistence and frontend code are not included.

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
    source_photo_id="return1", category=ConditionCategory.SCRATCH,
    severity=Severity.MINOR, confidence=0.65,
    review_state=ReviewState.NEEDS_REVIEW,
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
