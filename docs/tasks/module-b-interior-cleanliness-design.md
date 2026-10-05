# Module B interior-cleanliness model design

## Objective

Analyze one `INTERIOR_FRONT` or `INTERIOR_REAR` RGB photo and decide whether
visible stain or dirt is present. The model is independent of the exterior
scratch/collision checkpoint. Module B owns inference and converts a positive
result into a Module D `CLEANLINESS` finding. Module D continues to own review,
priority, workflow, and payment policy.

## Model and data

The model uses an LR-ASPP MobileNetV3-Large segmenter with internal pixel
classes `background`, `stain`, and `dirt`. An image-level binary gate shares the
backbone after locally labelled Hotai interior photos are available. MoLa-VI v1
provides licensed pixel supervision; Hotai `clean`, `dirty`, and `uncertain`
labels provide deployment-domain supervision. `uncertain` samples are excluded
from supervised training.

Data is split by vehicle identity, not by image, with a fixed seed. Duplicate
and near-duplicate images are grouped by perceptual hash. The locked test set is
never used for model, epoch, or threshold selection.

## Output contract

The public single-photo API returns a `PhotoCleanlinessAssessment` containing
the photo ID, `dirty` or `no_visible_dirt_detected`, a finite model score,
optional stain/dirt evidence, review-only model status, and model version.
Only a `dirty` result becomes an `AIFinding` with category `cleanliness` and the
fixed business severity `minor`. An absence of detected dirt is not emitted as
a Module D Detection.

## Quality gate

Validation selects image and pixel gates. A deployable checkpoint requires both
dirty recall and clean specificity of at least 0.80 on the vehicle-grouped
locked test. Otherwise the artifact remains diagnostic and review-only. The
reported metrics include the binary confusion matrix, recall, specificity,
precision, NPV, balanced accuracy, PR-AUC, stain/dirt pixel IoU, and CPU/GPU
latency.

## Integration

`CaseBuildingModuleB` remains backward compatible with its existing damage
analyzer and accepts an optional cleanliness analyzer. Exterior and
`OTHER_DAMAGE` photos go only to the damage analyzer. Return-side interior
photos go only to the cleanliness analyzer. Module E owns the second lazy model
provider and environment configuration. The existing HTTP request schema can
carry interior photo IDs without modification.
