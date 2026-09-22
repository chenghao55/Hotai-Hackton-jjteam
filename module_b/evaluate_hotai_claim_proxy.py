"""Evaluate the damage-to-claim-candidate rule on the private Hotai folders."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

from .damage_inference import load_damage_segmentation_model, predict_damage_assessment
from .dataset import discover_samples


def binary_metrics(truth: list[int], predictions: list[int]) -> dict[str, object]:
    if len(truth) != len(predictions) or not truth:
        raise ValueError("truth and predictions must be nonempty and equally sized")
    tp = sum(actual == 1 and predicted == 1 for actual, predicted in zip(truth, predictions, strict=True))
    tn = sum(actual == 0 and predicted == 0 for actual, predicted in zip(truth, predictions, strict=True))
    fp = sum(actual == 0 and predicted == 1 for actual, predicted in zip(truth, predictions, strict=True))
    fn = sum(actual == 1 and predicted == 0 for actual, predicted in zip(truth, predictions, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "accuracy": (tp + tn) / len(truth),
        "balanced_accuracy": (recall + specificity) / 2,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "false_positive_count": fp,
        "false_negative_count": fn,
    }


def evaluate_hotai_claim_proxy(
    data_root: Path, checkpoint_path: Path, output_path: Path, device: str = "auto"
) -> dict[str, object]:
    samples = discover_samples(data_root)
    bundle = load_damage_segmentation_model(checkpoint_path, device=device)
    rows: list[dict[str, object]] = []
    category_counts: Counter[str] = Counter()
    started = time.perf_counter()
    for index, sample in enumerate(samples, start=1):
        photo_id = sample.path.relative_to(data_root).as_posix()
        assessment = predict_damage_assessment(bundle, sample.path, photo_id)
        categories = [item.category for item in assessment.detections]
        category_counts.update(categories)
        rows.append(
            {
                "truth": sample.label,
                "prediction": int(assessment.damage_state == "damage_detected"),
                "group_id": sample.group_id,
                "categories": categories,
            }
        )
        if index % 25 == 0 or index == len(samples):
            print(json.dumps({"event": "progress", "completed": index, "total": len(samples)}), flush=True)

    image_metrics = binary_metrics(
        [int(row["truth"]) for row in rows],
        [int(row["prediction"]) for row in rows],
    )
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["group_id"]), []).append(row)
    group_truth: list[int] = []
    group_predictions: list[int] = []
    for group_id, items in grouped.items():
        labels = {int(item["truth"]) for item in items}
        if len(labels) != 1:
            raise ValueError(f"Vehicle group appears in both claim classes: {group_id}")
        group_truth.append(labels.pop())
        group_predictions.append(int(any(int(item["prediction"]) for item in items)))

    report = {
        "status": "experimental_review_only",
        "interpretation": {
            "positive_truth": "Hotai folder 進行索賠資料",
            "negative_truth": "Hotai folder 沒有進行索賠",
            "positive_prediction": "at least one scratch/collision_damage detection",
            "negative_prediction": "no_detected_damage",
            "warning": "This evaluates a claim-candidate proxy, not category accuracy or claim causality.",
        },
        "model_version": bundle.model_version,
        "checkpoint": str(checkpoint_path),
        "images": {"count": len(rows), **image_metrics},
        "vehicle_groups": {
            "count": len(grouped),
            "aggregation": "claim_candidate if any photo in the vehicle group has detected damage",
            **binary_metrics(group_truth, group_predictions),
        },
        "predicted_detection_counts": {
            **dict(category_counts),
            "multi_label_images": sum(len(row["categories"]) > 1 for row in rows),
            "no_detected_damage_images": sum(int(row["prediction"]) == 0 for row in rows),
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"event": "complete", "output": str(output_path), **report}, ensure_ascii=False), flush=True)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=Path("artifacts/module_b/damage_segmenter.pth"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/module_b/hotai_claim_proxy_metrics.json"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evaluate_hotai_claim_proxy(args.data_root, args.checkpoint, args.output, args.device)


if __name__ == "__main__":
    main()
