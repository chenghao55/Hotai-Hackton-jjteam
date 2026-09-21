# Module B single-photo calibration implementation plan

1. Add deterministic letterbox content masks and connected-component feature extraction with unit tests.
2. Add a serializable NumPy runtime calibrator and extend the damage bundle loader without breaking the v1 checkpoint.
3. Add grouped Hotai feature extraction, five-fold out-of-fold logistic calibration, recall-constrained threshold selection, locked-test evaluation, and v2 checkpoint export.
4. Route `predict_damage_assessment()` and low-level detections through the calibrator when present.
5. Update dependencies and Module B documentation.
6. Run all tests, train the calibrator on the local Hotai dataset, reload the checkpoint, and report OOF and locked-test false positives and false negatives.
