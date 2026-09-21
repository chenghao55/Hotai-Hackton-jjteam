"""Train a grouped single-photo damage calibrator on private Hotai weak labels."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import random
import time
from typing import Sequence

import numpy as np

from .annotate_hotai import AnnotatedPhotoSample, load_annotated_samples
from .damage_calibration import FEATURE_SCHEMA
from .damage_inference import extract_image_damage_features, load_damage_segmentation_model
from .dataset import ImageSample, discover_samples, split_locked_test
from .evaluate_hotai_claim_proxy import binary_metrics
from .train import make_group_cv_splits, set_seed


DEFAULT_SEED = 20260914
CALIBRATED_MODEL_VERSION = "lraspp-mobilenetv3-large-damage-calibrated-v2"


@dataclass(frozen=True)
class CalibrationConfig:
    seed: int = DEFAULT_SEED
    folds: int = 5
    test_fraction: float = 0.2
    minimum_oof_recall: float = 0.95
    logistic_c: float = 1.0
    max_iterations: int = 2_000


def _fit_linear_calibrator(features, labels, config: CalibrationConfig):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(features)
    classifier = LogisticRegression(
        C=config.logistic_c,
        class_weight="balanced",
        max_iter=config.max_iterations,
        random_state=config.seed,
        solver="lbfgs",
    ).fit(scaler.transform(features), labels)
    return scaler, classifier


def _predict_scores(scaler, classifier, features, has_evidence):
    scores = classifier.predict_proba(scaler.transform(features))[:, 1].astype(np.float64)
    # No connected damage component is always no_detected_damage by contract.
    scores = np.where(has_evidence, scores, 0.0)
    if not np.isfinite(scores).all():
        raise ValueError("Calibrator produced non-finite scores")
    return scores


def select_recall_constrained_threshold(
    scores: np.ndarray, labels: np.ndarray, minimum_recall: float
) -> tuple[float, dict[str, object]]:
    if scores.ndim != 1 or labels.ndim != 1 or len(scores) != len(labels) or not len(scores):
        raise ValueError("scores and labels must be nonempty equally sized vectors")
    if not 0 < minimum_recall <= 1 or not np.isin(labels, [0, 1]).all() or labels.sum() == 0:
        raise ValueError("threshold selection needs binary labels and a valid recall target")
    candidates = sorted({0.0, *(float(value) for value in scores if 0 <= value <= 1)})
    best: tuple[tuple[float, float, int, float], float, dict[str, object]] | None = None
    for threshold in candidates:
        predictions = (scores > threshold).astype(np.int64)
        metrics = binary_metrics(labels.tolist(), predictions.tolist())
        if float(metrics["recall"]) + 1e-12 < minimum_recall:
            continue
        key = (
            float(metrics["specificity"]),
            float(metrics["precision"]),
            -int(metrics["false_positive_count"]),
            threshold,
        )
        if best is None or key > best[0]:
            best = (key, threshold, metrics)
    if best is None:
        raise ValueError("No calibration threshold satisfies the minimum OOF recall")
    return best[1], best[2]


def _report(scores, labels, threshold):
    predictions = (scores > threshold).astype(np.int64)
    report = binary_metrics(labels.tolist(), predictions.tolist())
    negatives = int(np.sum(labels == 0))
    report.update(
        {
            "threshold": threshold,
            "false_positive_rate": (
                int(report["false_positive_count"]) / negatives if negatives else 0.0
            ),
            "sample_count": int(len(labels)),
            "positive_count": int(labels.sum()),
            "negative_count": negatives,
        }
    )
    return report


def _group_hash(samples: list[ImageSample]) -> str:
    canonical = "\n".join(sorted({sample.group_id for sample in samples}))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_annotated_locked_test(
    samples: Sequence[AnnotatedPhotoSample], *, seed: int, test_fraction: float
) -> tuple[list[AnnotatedPhotoSample], list[AnnotatedPhotoSample]]:
    """Search a deterministic group split that preserves both image labels."""
    groups: dict[str, list[AnnotatedPhotoSample]] = {}
    for sample in samples:
        groups.setdefault(sample.group_id, []).append(sample)
    group_ids = sorted(groups)
    test_group_count = max(1, round(len(group_ids) * test_fraction))
    overall_ratio = sum(sample.label for sample in samples) / len(samples)
    rng = random.Random(seed)
    best = None
    for _ in range(10_000):
        shuffled = group_ids.copy()
        rng.shuffle(shuffled)
        test_groups = set(shuffled[:test_group_count])
        test = [sample for group in sorted(test_groups) for sample in groups[group]]
        development = [sample for group in group_ids if group not in test_groups for sample in groups[group]]
        if {sample.label for sample in test} != {0, 1} or {sample.label for sample in development} != {0, 1}:
            continue
        score = abs(len(test) / len(samples) - test_fraction) + abs(
            sum(sample.label for sample in test) / len(test) - overall_ratio
        )
        candidate = (score, sorted(test_groups), development, test)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        raise ValueError("Unable to create a grouped annotated locked-test split")
    return best[2], best[3]


def extract_dataset_features(samples, bundle):
    features = np.zeros((len(samples), len(FEATURE_SCHEMA)), dtype=np.float64)
    has_evidence = np.zeros(len(samples), dtype=bool)
    evidence_categories: list[tuple[str, ...]] = []
    started = time.perf_counter()
    for index, sample in enumerate(samples):
        result = extract_image_damage_features(bundle, sample.path)
        features[index] = result.values
        has_evidence[index] = bool(result.evidence)
        evidence_categories.append(tuple(result.evidence))
        completed = index + 1
        if completed % 25 == 0 or completed == len(samples):
            print(json.dumps({"event": "feature_progress", "completed": completed, "total": len(samples)}), flush=True)
    return features, has_evidence, evidence_categories, time.perf_counter() - started


def category_report(samples, evidence_categories, damage_predictions):
    report = {}
    for category in ("scratch", "collision_damage"):
        truth = [int(category in sample.categories) for sample in samples]
        predictions = [
            int(bool(damage) and category in evidence)
            for damage, evidence in zip(damage_predictions, evidence_categories, strict=True)
        ]
        report[category] = binary_metrics(truth, predictions)
        report[category]["positive_count"] = sum(truth)
    return report


def train_damage_calibrator(
    data_root: Path,
    base_checkpoint: Path,
    output_dir: Path,
    config: CalibrationConfig,
    device: str,
    queue_path: Path | None = None,
    annotations_path: Path | None = None,
) -> Path:
    import torch

    set_seed(config.seed)
    if (queue_path is None) != (annotations_path is None):
        raise ValueError("queue_path and annotations_path must be provided together")
    if queue_path is not None and annotations_path is not None:
        samples = load_annotated_samples(queue_path, annotations_path)
        development, locked_test = split_annotated_locked_test(
            samples, seed=config.seed, test_fraction=config.test_fraction
        )
        label_source = "manual_visible_damage"
    else:
        samples = discover_samples(data_root, validate_images=True)
        development, locked_test = split_locked_test(
            samples, seed=config.seed, test_fraction=config.test_fraction
        )
        label_source = "claim_folder_weak_label"
    bundle = load_damage_segmentation_model(base_checkpoint, device=device)
    all_features, all_evidence, all_categories, feature_seconds = extract_dataset_features(samples, bundle)
    feature_by_path = {
        sample.path: (all_features[index], all_evidence[index], all_categories[index])
        for index, sample in enumerate(samples)
    }

    development_features = np.asarray([feature_by_path[s.path][0] for s in development])
    development_evidence = np.asarray([feature_by_path[s.path][1] for s in development])
    development_categories = [feature_by_path[s.path][2] for s in development]
    development_labels = np.asarray([s.label for s in development], dtype=np.int64)
    splits = make_group_cv_splits(development, folds=config.folds, seed=config.seed)
    oof_scores = np.full(len(development), np.nan, dtype=np.float64)
    for fold, (train_indices, validation_indices) in enumerate(splits, start=1):
        scaler, classifier = _fit_linear_calibrator(
            development_features[train_indices], development_labels[train_indices], config
        )
        oof_scores[validation_indices] = _predict_scores(
            scaler,
            classifier,
            development_features[validation_indices],
            development_evidence[validation_indices],
        )
        print(json.dumps({"event": "fold_complete", "fold": fold}), flush=True)
    if not np.isfinite(oof_scores).all():
        raise RuntimeError("OOF calibration scores are incomplete")

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "damage_calibration_metrics.json"
    try:
        threshold, _ = select_recall_constrained_threshold(
            oof_scores, development_labels, config.minimum_oof_recall
        )
    except ValueError:
        report = {
            "status": "quality_gate_failed",
            "reason": "No OOF threshold satisfies the minimum recall target",
            "config": asdict(config),
        }
        metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    oof_report = _report(oof_scores, development_labels, threshold)
    if float(oof_report["false_positive_rate"]) >= 1.0:
        report = {
            "status": "quality_gate_failed",
            "reason": "OOF false-positive rate did not improve over the 100% baseline",
            "config": asdict(config),
            "selected_threshold": threshold,
            "oof": oof_report,
        }
        metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError(report["reason"])

    final_scaler, final_classifier = _fit_linear_calibrator(
        development_features, development_labels, config
    )
    test_features = np.asarray([feature_by_path[s.path][0] for s in locked_test])
    test_evidence = np.asarray([feature_by_path[s.path][1] for s in locked_test])
    test_categories = [feature_by_path[s.path][2] for s in locked_test]
    test_labels = np.asarray([s.label for s in locked_test], dtype=np.int64)
    test_scores = _predict_scores(final_scaler, final_classifier, test_features, test_evidence)
    test_report = _report(test_scores, test_labels, threshold)
    oof_category_report = (
        category_report(development, development_categories, oof_scores > threshold)
        if label_source == "manual_visible_damage"
        else None
    )
    test_category_report = (
        category_report(locked_test, test_categories, test_scores > threshold)
        if label_source == "manual_visible_damage"
        else None
    )
    if float(test_report["specificity"]) <= 0.0:
        report = {
            "status": "quality_gate_failed",
            "reason": "Locked-test specificity did not improve over the all-positive baseline",
            "label_source": label_source,
            "dataset": {
                "total": len(samples),
                "development": len(development),
                "locked_test": len(locked_test),
                "development_groups": len({s.group_id for s in development}),
                "locked_test_groups": len({s.group_id for s in locked_test}),
            },
            "config": asdict(config),
            "selected_threshold": threshold,
            "oof": oof_report,
            "locked_test": test_report,
            "category_metrics": {
                "oof": oof_category_report,
                "locked_test": test_category_report,
            },
        }
        metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError(report["reason"])

    calibration = {
        "feature_schema": list(FEATURE_SCHEMA),
        "mean": final_scaler.mean_.astype(float).tolist(),
        "scale": final_scaler.scale_.astype(float).tolist(),
        "coefficients": final_classifier.coef_[0].astype(float).tolist(),
        "intercept": float(final_classifier.intercept_[0]),
        "threshold": threshold,
    }
    base = torch.load(base_checkpoint, map_location="cpu", weights_only=True)
    base["model_version"] = CALIBRATED_MODEL_VERSION
    base["calibration"] = calibration
    base["calibration_training"] = {
        "seed": config.seed,
        "source_checkpoint_sha256": _file_hash(base_checkpoint),
        "locked_groups_sha256": _group_hash(locked_test),
        "label_source": label_source,
        "development_metrics": oof_report,
        "locked_test_metrics": test_report,
    }
    checkpoint_path = output_dir / "damage_calibrated.pth"
    torch.save(base, checkpoint_path)

    report = {
        "status": "experimental_review_only",
        "model_version": CALIBRATED_MODEL_VERSION,
        "device": str(bundle.device),
        "feature_extraction_seconds": feature_seconds,
        "label_source": label_source,
        "dataset": {
            "total": len(samples),
            "development": len(development),
            "locked_test": len(locked_test),
            "development_groups": len({s.group_id for s in development}),
            "locked_test_groups": len({s.group_id for s in locked_test}),
        },
        "config": asdict(config),
        "selected_threshold": threshold,
        "oof": oof_report,
        "locked_test": test_report,
        "category_metrics": {
            "oof": oof_category_report,
            "locked_test": test_category_report,
        },
    }
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    load_damage_segmentation_model(checkpoint_path, device="cpu")
    print(json.dumps({"event": "complete", "checkpoint": str(checkpoint_path), **report}), flush=True)
    return checkpoint_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, default=Path("artifacts/module_b/damage_segmenter.pth"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/module_b"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--minimum-oof-recall", type=float, default=0.95)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--annotations", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = CalibrationConfig(minimum_oof_recall=args.minimum_oof_recall)
    train_damage_calibrator(
        args.data_root,
        args.base_checkpoint,
        args.output_dir,
        config,
        args.device,
        args.queue,
        args.annotations,
    )


if __name__ == "__main__":
    main()
