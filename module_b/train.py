"""Train and validate the conservative single-image claim classifier."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import statistics
import time
from typing import Sequence

import numpy as np

from .dataset import ClaimImageDataset, ImageSample, discover_samples, split_locked_test
from .model import (
    ARCHITECTURE,
    DEFAULT_IMAGE_SIZE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_model,
    build_transform,
    freeze_backbone,
    unfreeze_last_feature_blocks,
)


DEFAULT_SEED = 20260914
MODEL_VERSION = "mobilenetv3-large-claim-v1"


@dataclass(frozen=True)
class TrainConfig:
    seed: int = DEFAULT_SEED
    image_size: int = DEFAULT_IMAGE_SIZE
    batch_size: int = 16
    workers: int = 0
    folds: int = 5
    head_epochs: int = 10
    finetune_epochs: int = 30
    patience: int = 7
    head_learning_rate: float = 1e-3
    backbone_learning_rate: float = 1e-5
    finetune_head_learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    test_fraction: float = 0.2


def set_seed(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def resolve_device(requested: str):
    import torch

    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested not in {"cpu", "cuda"}:
        raise ValueError("device must be 'auto', 'cpu', or 'cuda'")
    if requested == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA requested but unavailable")
    return torch.device(requested)


def make_loader(
    samples: Sequence[ImageSample],
    *,
    training: bool,
    config: TrainConfig,
    seed: int,
):
    import torch
    from torch.utils.data import DataLoader

    dataset = ClaimImageDataset(
        samples,
        build_transform(training=training, image_size=config.image_size),
    )
    generator = torch.Generator().manual_seed(seed)
    return DataLoader(
        dataset,
        batch_size=config.batch_size,
        shuffle=training,
        num_workers=config.workers,
        pin_memory=torch.cuda.is_available(),
        generator=generator,
    )


def positive_weight(samples: Sequence[ImageSample], device):
    import torch

    positives = sum(sample.label for sample in samples)
    negatives = len(samples) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("Training samples must contain both labels")
    return torch.tensor([negatives / positives], dtype=torch.float32, device=device)


def make_group_cv_splits(
    samples: Sequence[ImageSample], *, folds: int, seed: int
) -> list[tuple[np.ndarray, np.ndarray]]:
    from sklearn.model_selection import StratifiedGroupKFold

    labels = np.asarray([sample.label for sample in samples])
    groups = np.asarray([sample.group_id for sample in samples])
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    splits = list(splitter.split(np.zeros(len(samples)), labels, groups))
    for train_indices, validation_indices in splits:
        train_groups = set(groups[train_indices])
        validation_groups = set(groups[validation_indices])
        if not train_groups.isdisjoint(validation_groups):
            raise RuntimeError("Vehicle group leaked across a CV fold")
    return splits


def evaluate(model, samples: Sequence[ImageSample], config: TrainConfig, device):
    import torch

    model.eval()
    loader = make_loader(samples, training=False, config=config, seed=config.seed)
    logits: list[float] = []
    labels: list[int] = []
    with torch.inference_mode():
        for images, batch_labels, _ in loader:
            output = model(images.to(device, non_blocking=True)).reshape(-1)
            logits.extend(float(value) for value in output.detach().cpu())
            labels.extend(int(value) for value in batch_labels)
    return np.asarray(logits, dtype=np.float64), np.asarray(labels, dtype=np.int64)


def validation_loss(model, samples: Sequence[ImageSample], config: TrainConfig, device, criterion) -> float:
    import torch

    model.eval()
    loader = make_loader(samples, training=False, config=config, seed=config.seed)
    total_loss = 0.0
    total_items = 0
    with torch.inference_mode():
        for images, labels, _ in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            logits = model(images).reshape(-1)
            loss = criterion(logits, labels)
            total_loss += float(loss.item()) * len(labels)
            total_items += len(labels)
    return total_loss / total_items


def _train_epoch(model, loader, optimizer, criterion, device, scaler, frozen_prefix: int | None) -> float:
    import torch

    model.train()
    if frozen_prefix is not None:
        for block in model.features[:frozen_prefix]:
            block.eval()
    total_loss = 0.0
    total_items = 0
    for images, labels, _ in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type=device.type, enabled=device.type == "cuda"):
            logits = model(images).reshape(-1)
            loss = criterion(logits, labels)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        total_loss += float(loss.item()) * len(labels)
        total_items += len(labels)
    return total_loss / total_items


def fit_stage(
    model,
    train_samples: Sequence[ImageSample],
    validation_samples: Sequence[ImageSample],
    optimizer,
    criterion,
    *,
    epochs: int,
    patience: int,
    config: TrainConfig,
    device,
    seed: int,
    frozen_prefix: int | None,
) -> tuple[int, float]:
    import torch

    loader = make_loader(train_samples, training=True, config=config, seed=seed)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best_state = deepcopy(model.state_dict())
    best_loss = math.inf
    best_epoch = 0
    stale_epochs = 0
    for epoch in range(epochs):
        train_loss = _train_epoch(
            model, loader, optimizer, criterion, device, scaler, frozen_prefix
        )
        current_loss = validation_loss(model, validation_samples, config, device, criterion)
        print(
            json.dumps(
                {
                    "event": "epoch",
                    "epoch": epoch + 1,
                    "train_loss": train_loss,
                    "validation_loss": current_loss,
                }
            ),
            flush=True,
        )
        if current_loss < best_loss - 1e-6:
            best_loss = current_loss
            best_epoch = epoch + 1
            best_state = deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break
    model.load_state_dict(best_state)
    return best_epoch, best_loss


def train_fold(
    train_samples: Sequence[ImageSample],
    validation_samples: Sequence[ImageSample],
    *,
    config: TrainConfig,
    device,
    seed: int,
):
    import torch

    set_seed(seed)
    model = build_model(pretrained=True).to(device)
    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=positive_weight(train_samples, device))

    freeze_backbone(model)
    optimizer = torch.optim.AdamW(
        model.classifier.parameters(),
        lr=config.head_learning_rate,
        weight_decay=config.weight_decay,
    )
    head_epoch, _ = fit_stage(
        model,
        train_samples,
        validation_samples,
        optimizer,
        criterion,
        epochs=config.head_epochs,
        patience=config.patience,
        config=config,
        device=device,
        seed=seed,
        frozen_prefix=len(model.features),
    )

    unfreeze_last_feature_blocks(model, 3)
    optimizer = torch.optim.AdamW(
        [
            {"params": model.features[-3:].parameters(), "lr": config.backbone_learning_rate},
            {"params": model.classifier.parameters(), "lr": config.finetune_head_learning_rate},
        ],
        weight_decay=config.weight_decay,
    )
    finetune_epoch, _ = fit_stage(
        model,
        train_samples,
        validation_samples,
        optimizer,
        criterion,
        epochs=config.finetune_epochs,
        patience=config.patience,
        config=config,
        device=device,
        seed=seed + 1,
        frozen_prefix=len(model.features) - 3,
    )
    return model, head_epoch, finetune_epoch


def fit_fixed_epochs(
    model,
    samples: Sequence[ImageSample],
    *,
    config: TrainConfig,
    device,
    head_epochs: int,
    finetune_epochs: int,
):
    import torch

    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=positive_weight(samples, device))
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    freeze_backbone(model)
    optimizer = torch.optim.AdamW(
        model.classifier.parameters(), lr=config.head_learning_rate, weight_decay=config.weight_decay
    )
    loader = make_loader(samples, training=True, config=config, seed=config.seed)
    for _ in range(max(1, head_epochs)):
        _train_epoch(model, loader, optimizer, criterion, device, scaler, len(model.features))

    unfreeze_last_feature_blocks(model, 3)
    optimizer = torch.optim.AdamW(
        [
            {"params": model.features[-3:].parameters(), "lr": config.backbone_learning_rate},
            {"params": model.classifier.parameters(), "lr": config.finetune_head_learning_rate},
        ],
        weight_decay=config.weight_decay,
    )
    loader = make_loader(samples, training=True, config=config, seed=config.seed + 1)
    for _ in range(max(1, finetune_epochs)):
        _train_epoch(model, loader, optimizer, criterion, device, scaler, len(model.features) - 3)
    model.eval()
    return model


def sigmoid(values: np.ndarray) -> np.ndarray:
    positive = values >= 0
    result = np.empty_like(values)
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponential = np.exp(values[~positive])
    result[~positive] = exponential / (1.0 + exponential)
    return result


def zero_false_negative_threshold(probabilities: np.ndarray, labels: np.ndarray) -> float:
    positives = probabilities[labels == 1]
    if not len(positives):
        raise ValueError("Threshold selection requires positive examples")
    return float(np.nextafter(float(np.min(positives)), 0.0))


def classification_metrics(
    probabilities: np.ndarray, labels: np.ndarray, threshold: float
) -> dict[str, object]:
    from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score

    predictions = (probabilities >= threshold).astype(np.int64)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    negative_predictions = tn + fn
    return {
        "threshold": threshold,
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "false_negative_count": int(fn),
        "false_positive_count": int(fp),
        "claim_recall": float(recall_score(labels, predictions, zero_division=0)),
        "claim_precision": float(precision_score(labels, predictions, zero_division=0)),
        "no_claim_npv": float(tn / negative_predictions) if negative_predictions else None,
        "no_claim_coverage": float(negative_predictions / len(labels)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "sample_count": int(len(labels)),
        "positive_count": int(np.sum(labels)),
    }


def benchmark_model(model, config: TrainConfig, device) -> float:
    import torch

    benchmark_model_instance = build_model(pretrained=False)
    benchmark_model_instance.load_state_dict(model.state_dict())
    benchmark_model_instance.to(device).eval()
    tensor = torch.zeros(
        (1, 3, config.image_size, config.image_size), dtype=torch.float32, device=device
    )

    def synchronize() -> None:
        if device.type == "cuda":
            torch.cuda.synchronize(device)

    with torch.inference_mode():
        for _ in range(5):
            benchmark_model_instance(tensor)
        synchronize()
        durations = []
        for _ in range(20):
            synchronize()
            started = time.perf_counter()
            benchmark_model_instance(tensor)
            synchronize()
            durations.append((time.perf_counter() - started) * 1000.0)
    return float(statistics.median(durations))


def train(data_root: Path, output_dir: Path, config: TrainConfig, device_name: str) -> Path:
    import torch

    set_seed(config.seed)
    device = resolve_device(device_name)
    samples = discover_samples(data_root, validate_images=True)
    development, locked_test = split_locked_test(
        samples, seed=config.seed, test_fraction=config.test_fraction
    )
    labels = np.asarray([sample.label for sample in development])
    splits = make_group_cv_splits(development, folds=config.folds, seed=config.seed)

    oof_logits = np.full(len(development), np.nan, dtype=np.float64)
    best_head_epochs: list[int] = []
    best_finetune_epochs: list[int] = []
    for fold, (train_indices, validation_indices) in enumerate(
        splits, start=1
    ):
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
        best_head_epochs.append(head_epoch)
        best_finetune_epochs.append(finetune_epoch)
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    if not np.isfinite(oof_logits).all():
        raise RuntimeError("OOF predictions are incomplete")
    oof_probabilities = sigmoid(oof_logits)
    oof_threshold = zero_false_negative_threshold(oof_probabilities, labels)
    oof_metrics = classification_metrics(oof_probabilities, labels, oof_threshold)

    final_head_epochs = max(1, round(statistics.median(best_head_epochs)))
    final_finetune_epochs = max(1, round(statistics.median(best_finetune_epochs)))
    set_seed(config.seed)
    final_model = build_model(pretrained=True).to(device)
    fit_fixed_epochs(
        final_model,
        development,
        config=config,
        device=device,
        head_epochs=final_head_epochs,
        finetune_epochs=final_finetune_epochs,
    )

    development_logits, development_labels = evaluate(final_model, development, config, device)
    development_probabilities = sigmoid(development_logits)
    final_safe_threshold = zero_false_negative_threshold(
        development_probabilities, development_labels
    )
    deployment_threshold = min(oof_threshold, final_safe_threshold)

    test_logits, test_labels = evaluate(final_model, locked_test, config, device)
    test_probabilities = sigmoid(test_logits)
    test_metrics = classification_metrics(test_probabilities, test_labels, deployment_threshold)
    passed = (
        oof_metrics["false_negative_count"] == 0
        and test_metrics["false_negative_count"] == 0
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "claim_model.pth"
    metrics_path = output_dir / "metrics.json"
    checkpoint = {
        "model_state_dict": {key: value.detach().cpu() for key, value in final_model.state_dict().items()},
        "architecture": ARCHITECTURE,
        "model_version": MODEL_VERSION,
        "image_size": config.image_size,
        "normalization": {"mean": list(IMAGENET_MEAN), "std": list(IMAGENET_STD)},
        "label_mapping": {"no_claim": 0, "claim": 1},
        "threshold": deployment_threshold,
        "seed": config.seed,
        "status": "experimental" if passed else "review_only",
        "training_config": asdict(config),
        "metrics": {"oof": oof_metrics, "locked_test": test_metrics},
    }
    torch.save(checkpoint, checkpoint_path)

    report = {
        "model_version": MODEL_VERSION,
        "status": checkpoint["status"],
        "device": str(device),
        "dataset": {
            "total_samples": len(samples),
            "negative_samples": sum(sample.label == 0 for sample in samples),
            "positive_samples": sum(sample.label == 1 for sample in samples),
            "development_samples": len(development),
            "locked_test_samples": len(locked_test),
            "development_groups": len(set(sample.group_id for sample in development)),
            "locked_test_groups": len(set(sample.group_id for sample in locked_test)),
        },
        "selected_epochs": {
            "head": final_head_epochs,
            "finetune": final_finetune_epochs,
        },
        "oof": oof_metrics,
        "locked_test": test_metrics,
        "cpu_median_latency_ms": benchmark_model(
            final_model, config, torch.device("cpu")
        ),
        "gpu_median_latency_ms": (
            benchmark_model(final_model, config, device)
            if device.type == "cuda"
            else None
        ),
    }
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    from .inference import load_claim_model

    load_claim_model(checkpoint_path, device="cpu")
    print(json.dumps({"event": "complete", "checkpoint": str(checkpoint_path), **report}), flush=True)
    return checkpoint_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/module_b"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--head-epochs", type=int, default=10)
    parser.add_argument("--finetune-epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = TrainConfig(
        seed=args.seed,
        batch_size=args.batch_size,
        workers=args.workers,
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
        patience=args.patience,
    )
    train(args.data_root, args.output_dir, config, args.device)


if __name__ == "__main__":
    main()
