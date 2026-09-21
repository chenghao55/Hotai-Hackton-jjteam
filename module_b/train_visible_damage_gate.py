"""Fine-tune a single-photo visible-damage gate from manual Hotai labels."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import statistics

import numpy as np

from .annotate_hotai import load_annotated_samples
from .condition_schema import MODEL_STATUS
from .damage_inference import load_damage_segmentation_model, predict_damage_conditions
from .evaluate_hotai_claim_proxy import binary_metrics
from .model import ARCHITECTURE, IMAGENET_MEAN, IMAGENET_STD, build_model
from .train import (
    TrainConfig,
    evaluate,
    fit_fixed_epochs,
    make_group_cv_splits,
    set_seed,
    sigmoid,
    train_fold,
)
from .train_damage_calibrator import (
    category_report,
    select_recall_constrained_threshold,
    split_annotated_locked_test,
)


MODEL_VERSION = "mobilenetv3-large-visible-damage-gate-v1"
COMBINED_MODEL_VERSION = "lraspp-mobilenetv3-large-damage-gated-v3"


def _group_hash(samples) -> str:
    value = "\n".join(sorted({sample.group_id for sample in samples}))
    return sha256(value.encode("utf-8")).hexdigest()


def _metrics(probabilities, labels, threshold):
    predictions = (probabilities > threshold).astype(np.int64)
    result = binary_metrics(labels.tolist(), predictions.tolist())
    negatives = int(np.sum(labels == 0))
    result.update(
        {
            "threshold": threshold,
            "false_positive_rate": (
                int(result["false_positive_count"]) / negatives if negatives else 0.0
            ),
            "sample_count": int(len(labels)),
            "positive_count": int(labels.sum()),
            "negative_count": negatives,
        }
    )
    return result


def train_visible_damage_gate(
    queue_path: Path,
    annotations_path: Path,
    base_checkpoint: Path,
    output_dir: Path,
    config: TrainConfig,
    device_name: str,
    minimum_oof_recall: float,
) -> Path:
    import torch

    from .train import resolve_device

    set_seed(config.seed)
    samples = load_annotated_samples(queue_path, annotations_path)
    development, locked_test = split_annotated_locked_test(
        samples, seed=config.seed, test_fraction=config.test_fraction
    )
    device = resolve_device(device_name)
    development_labels = np.asarray([sample.label for sample in development], dtype=np.int64)
    splits = make_group_cv_splits(development, folds=config.folds, seed=config.seed)
    oof_logits = np.full(len(development), np.nan, dtype=np.float64)
    head_epochs: list[int] = []
    finetune_epochs: list[int] = []
    for fold, (train_indices, validation_indices) in enumerate(splits, start=1):
        print(json.dumps({"event": "fold_start", "fold": fold}), flush=True)
        train_samples = [development[index] for index in train_indices]
        validation_samples = [development[index] for index in validation_indices]
        model, head_epoch, finetune_epoch = train_fold(
            train_samples,
            validation_samples,
            config=config,
            device=device,
            seed=config.seed + fold * 100,
        )
        fold_logits, _ = evaluate(model, validation_samples, config, device)
        oof_logits[validation_indices] = fold_logits
        head_epochs.append(head_epoch)
        finetune_epochs.append(finetune_epoch)
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
    if not np.isfinite(oof_logits).all():
        raise RuntimeError("Visible-damage OOF predictions are incomplete")
    oof_probabilities = sigmoid(oof_logits)
    threshold, _ = select_recall_constrained_threshold(
        oof_probabilities, development_labels, minimum_oof_recall
    )
    oof_report = _metrics(oof_probabilities, development_labels, threshold)

    selected_head_epochs = max(1, round(statistics.median(head_epochs)))
    selected_finetune_epochs = max(1, round(statistics.median(finetune_epochs)))
    set_seed(config.seed)
    final_model = build_model(pretrained=True).to(device)
    fit_fixed_epochs(
        final_model,
        development,
        config=config,
        device=device,
        head_epochs=selected_head_epochs,
        finetune_epochs=selected_finetune_epochs,
    )
    test_logits, test_labels = evaluate(final_model, locked_test, config, device)
    test_probabilities = sigmoid(test_logits)
    test_report = _metrics(test_probabilities, test_labels, threshold)

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "visible_damage_gate_metrics.json"
    report = {
        "status": MODEL_STATUS,
        "model_version": MODEL_VERSION,
        "device": str(device),
        "dataset": {
            "total": len(samples),
            "development": len(development),
            "locked_test": len(locked_test),
            "development_groups": len({sample.group_id for sample in development}),
            "locked_test_groups": len({sample.group_id for sample in locked_test}),
        },
        "selected_epochs": {
            "head": selected_head_epochs,
            "finetune": selected_finetune_epochs,
        },
        "minimum_oof_recall": minimum_oof_recall,
        "oof": oof_report,
        "locked_test": test_report,
        "config": asdict(config),
    }
    if float(oof_report["specificity"]) <= 0 or float(test_report["specificity"]) <= 0:
        report["status"] = "quality_gate_failed"
        report["reason"] = "Visible-damage gate did not reject any locked no-damage images"
        metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError(report["reason"])

    base = torch.load(base_checkpoint, map_location="cpu", weights_only=True)
    base["model_version"] = COMBINED_MODEL_VERSION
    base["visible_damage_gate"] = {
        "model_state_dict": {
            key: value.detach().cpu() for key, value in final_model.state_dict().items()
        },
        "architecture": ARCHITECTURE,
        "model_version": MODEL_VERSION,
        "image_size": config.image_size,
        "normalization": {"mean": list(IMAGENET_MEAN), "std": list(IMAGENET_STD)},
        "threshold": threshold,
        "label_mapping": {"no_detected_damage": 0, "damage_detected": 1},
    }
    base["visible_damage_gate_training"] = {
        "seed": config.seed,
        "locked_groups_sha256": _group_hash(locked_test),
        "oof": oof_report,
        "locked_test": test_report,
    }
    checkpoint_path = output_dir / "damage_with_gate.pth"
    torch.save(base, checkpoint_path)
    bundle = load_damage_segmentation_model(checkpoint_path, device=device_name)
    emitted_categories = []
    damage_predictions = []
    for sample in locked_test:
        detections = predict_damage_conditions(bundle, sample.path, sample.annotation_id)
        emitted_categories.append(tuple(item.category for item in detections))
        damage_predictions.append(bool(detections))
    report["category_metrics_locked_test"] = category_report(
        locked_test, emitted_categories, damage_predictions
    )
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    load_damage_segmentation_model(checkpoint_path, device="cpu")
    print(json.dumps({"event": "complete", "checkpoint": str(checkpoint_path), **report}), flush=True)
    return checkpoint_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=Path("data/hotai_annotation_queue.json"))
    parser.add_argument("--annotations", type=Path, default=Path("data/hotai_annotations.json"))
    parser.add_argument("--base-checkpoint", type=Path, default=Path("artifacts/module_b/damage_segmenter.pth"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/module_b"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--minimum-oof-recall", type=float, default=0.95)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--head-epochs", type=int, default=10)
    parser.add_argument("--finetune-epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = replace(
        TrainConfig(),
        batch_size=args.batch_size,
        workers=args.workers,
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
        patience=args.patience,
    )
    train_visible_damage_gate(
        args.queue,
        args.annotations,
        args.base_checkpoint,
        args.output_dir,
        config,
        args.device,
        args.minimum_oof_recall,
    )


if __name__ == "__main__":
    main()
