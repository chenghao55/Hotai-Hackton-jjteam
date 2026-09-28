"""Fine-tune LR-ASPP MobileNetV3-Large on licensed HITL damage polygons."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
from typing import Sequence

import numpy as np

from .condition_schema import MODEL_STATUS, REVIEW_STATE, SEVERITY_BY_CATEGORY
from .damage_inference import (
    DAMAGE_TASK_NAME,
    load_damage_segmentation_model,
)
from .damage_segmentation import (
    DAMAGE_CATEGORIES,
    DAMAGE_PIXEL_CLASSES,
    DamageSegmentationDataset,
    DamageSegmentationSample,
    load_damage_samples,
    split_damage_samples,
)
from .model import (
    DAMAGE_IMAGE_SIZE,
    DAMAGE_SEGMENTATION_ARCHITECTURE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_damage_segmentation_model,
    freeze_damage_backbone,
    unfreeze_last_damage_blocks,
)
from .train import resolve_device, set_seed


DEFAULT_SEED = 20260914
MODEL_VERSION = "lraspp-mobilenetv3-large-damage-v1"


@dataclass(frozen=True)
class DamageTrainConfig:
    seed: int = DEFAULT_SEED
    image_size: int = DAMAGE_IMAGE_SIZE
    batch_size: int = 4
    workers: int = 0
    head_epochs: int = 10
    finetune_epochs: int = 30
    patience: int = 7
    head_learning_rate: float = 1e-3
    backbone_learning_rate: float = 1e-5
    finetune_head_learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    validation_fraction: float = 0.2
    test_fraction: float = 0.2
    threshold_candidates: tuple[float, ...] = tuple(float(x) for x in np.linspace(0.1, 0.9, 17))
    area_candidates: tuple[int, ...] = (16, 64, 256)


def make_loader(samples: Sequence[DamageSegmentationSample], *, training: bool, config: DamageTrainConfig, seed: int):
    import torch
    from torch.utils.data import DataLoader

    generator = torch.Generator().manual_seed(seed)
    return DataLoader(
        DamageSegmentationDataset(samples, training=training, image_size=config.image_size),
        batch_size=config.batch_size,
        shuffle=training,
        num_workers=config.workers,
        pin_memory=torch.cuda.is_available(),
        generator=generator,
    )


def calculate_class_weights(samples, config, device):
    import torch

    counts = torch.zeros(len(DAMAGE_PIXEL_CLASSES), dtype=torch.float64)
    loader = make_loader(samples, training=False, config=config, seed=config.seed)
    for _, masks, _ in loader:
        counts += torch.bincount(masks.reshape(-1), minlength=len(DAMAGE_PIXEL_CLASSES))
    if torch.any(counts == 0):
        missing = [DAMAGE_PIXEL_CLASSES[i] for i, value in enumerate(counts) if value == 0]
        raise ValueError(f"Training split has no pixels for: {missing}")
    frequencies = counts / counts.sum()
    weights = torch.rsqrt(frequencies)
    weights = (weights / weights.mean()).clamp(max=20.0)
    return weights.to(device=device, dtype=torch.float32)


def _run_epoch(model, loader, criterion, device, optimizer=None, scaler=None, frozen_blocks=0):
    import torch

    training = optimizer is not None
    model.train(training)
    if training and frozen_blocks:
        for block in list(model.backbone.children())[:frozen_blocks]:
            block.eval()
    total_loss = 0.0
    total_items = 0
    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for images, masks, _ in loader:
            images = images.to(device, non_blocking=True)
            masks = masks.to(device, non_blocking=True)
            if training:
                optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=device.type == "cuda"):
                logits = model(images)["out"]
                loss = criterion(logits, masks)
            if training:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            total_loss += float(loss.item()) * len(images)
            total_items += len(images)
    return total_loss / total_items


def _fit_stage(model, train_samples, validation_samples, criterion, optimizer, *, epochs, config, device, seed, stage, frozen_blocks):
    import torch

    train_loader = make_loader(train_samples, training=True, config=config, seed=seed)
    validation_loader = make_loader(validation_samples, training=False, config=config, seed=seed)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best_state = deepcopy(model.state_dict())
    best_loss = math.inf
    best_epoch = 0
    stale = 0
    for epoch in range(1, epochs + 1):
        train_loss = _run_epoch(model, train_loader, criterion, device, optimizer, scaler, frozen_blocks)
        validation_loss = _run_epoch(model, validation_loader, criterion, device)
        print(json.dumps({"event": "epoch", "stage": stage, "epoch": epoch, "train_loss": train_loss, "validation_loss": validation_loss}), flush=True)
        if validation_loss < best_loss - 1e-6:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
            if stale >= config.patience:
                break
    model.load_state_dict(best_state)
    return best_epoch, best_loss


def fit_model(train_samples, validation_samples, config, device):
    import torch

    set_seed(config.seed)
    model = build_damage_segmentation_model(pretrained_backbone=True).to(device)
    class_weights = calculate_class_weights(train_samples, config, device)
    criterion = torch.nn.CrossEntropyLoss(weight=class_weights)
    freeze_damage_backbone(model)
    optimizer = torch.optim.AdamW(model.classifier.parameters(), lr=config.head_learning_rate, weight_decay=config.weight_decay)
    head_epoch, _ = _fit_stage(
        model, train_samples, validation_samples, criterion, optimizer,
        epochs=config.head_epochs, config=config, device=device, seed=config.seed,
        stage="head", frozen_blocks=len(list(model.backbone.children())),
    )
    unfreeze_last_damage_blocks(model, 3)
    blocks = list(model.backbone.children())
    optimizer = torch.optim.AdamW(
        [
            {"params": [p for block in blocks[-3:] for p in block.parameters()], "lr": config.backbone_learning_rate},
            {"params": model.classifier.parameters(), "lr": config.finetune_head_learning_rate},
        ],
        weight_decay=config.weight_decay,
    )
    finetune_epoch, _ = _fit_stage(
        model, train_samples, validation_samples, criterion, optimizer,
        epochs=config.finetune_epochs, config=config, device=device, seed=config.seed + 1,
        stage="finetune", frozen_blocks=max(0, len(blocks) - 3),
    )
    return model.eval(), class_weights.detach().cpu().tolist(), head_epoch, finetune_epoch


def collect_probabilities(model, samples, config, device):
    import torch

    loader = make_loader(samples, training=False, config=config, seed=config.seed)
    probabilities: list[np.ndarray] = []
    labels: list[tuple[int, int]] = []
    confusion = np.zeros((3, 3), dtype=np.int64)
    model.eval()
    with torch.inference_mode():
        for images, masks, indices in loader:
            logits = model(images.to(device, non_blocking=True))["out"]
            batch_probabilities = torch.softmax(logits, dim=1).cpu().numpy()
            predictions = logits.argmax(dim=1).cpu().numpy()
            target = masks.numpy()
            for truth, predicted in zip(target, predictions, strict=True):
                confusion += np.bincount((truth.reshape(-1) * 3 + predicted.reshape(-1)), minlength=9).reshape(3, 3)
            probabilities.extend(batch_probabilities)
            labels.extend(samples[int(index)].labels for index in indices)
    return np.asarray(probabilities), np.asarray(labels, dtype=np.int64), confusion


def _binary_metrics(predictions: np.ndarray, labels: np.ndarray) -> dict[str, float | int | list[list[int]]]:
    tp = int(np.sum(predictions & (labels == 1)))
    tn = int(np.sum(~predictions & (labels == 0)))
    fp = int(np.sum(predictions & (labels == 0)))
    fn = int(np.sum(~predictions & (labels == 1)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f2 = 5 * precision * recall / (4 * precision + recall) if precision + recall else 0.0
    return {"confusion_matrix": [[tn, fp], [fn, tp]], "precision": precision, "recall": recall, "f1": f1, "f2": f2, "false_negative_count": fn}


def select_detection_gates(probabilities, labels, config):
    thresholds: dict[str, float] = {}
    min_areas: dict[str, int] = {}
    for class_index, category in enumerate(DAMAGE_CATEGORIES, start=1):
        best_key = (-1.0, -1.0, -1.0, 0.0, 0)
        best = (0.5, 64)
        for threshold in config.threshold_candidates:
            counts = (probabilities[:, class_index] > threshold).sum(axis=(1, 2))
            for area in config.area_candidates:
                metrics = _binary_metrics(counts >= area, labels[:, class_index - 1])
                key = (metrics["f2"], metrics["recall"], metrics["precision"], threshold, -area)
                if key > best_key:
                    best_key = key
                    best = (threshold, area)
        thresholds[category], min_areas[category] = best
    return thresholds, min_areas


def make_report(probabilities, labels, pixel_confusion, thresholds, min_areas):
    per_class = {}
    for class_index, category in enumerate(DAMAGE_CATEGORIES, start=1):
        counts = (probabilities[:, class_index] > thresholds[category]).sum(axis=(1, 2))
        metrics = _binary_metrics(counts >= min_areas[category], labels[:, class_index - 1])
        metrics.update({"probability_threshold": thresholds[category], "min_area_pixels": min_areas[category]})
        per_class[category] = metrics
    intersection = np.diag(pixel_confusion).astype(float)
    union = pixel_confusion.sum(axis=0) + pixel_confusion.sum(axis=1) - intersection
    iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
    return {"image_level": per_class, "pixel_confusion_matrix": pixel_confusion.tolist(), "pixel_iou": dict(zip(DAMAGE_PIXEL_CLASSES, iou.tolist(), strict=True))}


def benchmark_model(model, image_size: int, device) -> float:
    """Return median single-image forward latency in milliseconds."""
    import statistics
    import torch

    sample = torch.zeros(1, 3, image_size, image_size, device=device)
    for _ in range(3):
        with torch.inference_mode():
            model(sample)
    if device.type == "cuda":
        torch.cuda.synchronize()
    timings = []
    for _ in range(20):
        started = time.perf_counter()
        with torch.inference_mode():
            model(sample)
        if device.type == "cuda":
            torch.cuda.synchronize()
        timings.append((time.perf_counter() - started) * 1000)
    return statistics.median(timings)


def train_damage_segmentation(manifest_path: Path, output_dir: Path, config: DamageTrainConfig, device_name: str) -> Path:
    import torch

    manifest, samples = load_damage_samples(manifest_path)
    train_samples, validation_samples, test_samples = split_damage_samples(
        samples, seed=config.seed, validation_fraction=config.validation_fraction, test_fraction=config.test_fraction
    )
    device = resolve_device(device_name)
    started = time.perf_counter()
    model, class_weights, head_epoch, finetune_epoch = fit_model(train_samples, validation_samples, config, device)
    val_probabilities, val_labels, val_confusion = collect_probabilities(model, validation_samples, config, device)
    thresholds, min_areas = select_detection_gates(val_probabilities, val_labels, config)
    test_probabilities, test_labels, test_confusion = collect_probabilities(model, test_samples, config, device)
    metrics = {
        "validation": make_report(val_probabilities, val_labels, val_confusion, thresholds, min_areas),
        "locked_test": make_report(test_probabilities, test_labels, test_confusion, thresholds, min_areas),
    }
    latency_ms = {
        "cpu": benchmark_model(deepcopy(model).cpu().eval(), config.image_size, torch.device("cpu"))
    }
    if torch.cuda.is_available():
        cuda_model = model if device.type == "cuda" else deepcopy(model).cuda().eval()
        latency_ms["cuda"] = benchmark_model(cuda_model, config.image_size, torch.device("cuda"))
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "damage_segmenter.pth"
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "architecture": DAMAGE_SEGMENTATION_ARCHITECTURE,
        "task": DAMAGE_TASK_NAME,
        "model_version": MODEL_VERSION,
        "status": MODEL_STATUS,
        "image_size": config.image_size,
        "normalization": {"mean": IMAGENET_MEAN, "std": IMAGENET_STD},
        "preprocessing": "exif_transpose_rgb_resize_and_pad",
        "pixel_classes": list(DAMAGE_PIXEL_CLASSES),
        "probability_thresholds": thresholds,
        "min_area_pixels": min_areas,
        "severity_by_category": {category: SEVERITY_BY_CATEGORY[category] for category in DAMAGE_CATEGORIES},
        "review_state": REVIEW_STATE,
        "seed": config.seed,
        "dataset_manifest_sha256": manifest.sha256,
        "metrics": metrics,
        "latency_ms": latency_ms,
    }
    torch.save(checkpoint, checkpoint_path)
    report = {
        "status": MODEL_STATUS,
        "model_version": MODEL_VERSION,
        "device": str(device),
        "elapsed_seconds": time.perf_counter() - started,
        "dataset_manifest_sha256": manifest.sha256,
        "dataset": {"total": len(samples), "train": len(train_samples), "validation": len(validation_samples), "locked_test": len(test_samples)},
        "selected_epochs": {"head": head_epoch, "finetune": finetune_epoch},
        "class_weights": class_weights,
        "probability_thresholds": thresholds,
        "min_area_pixels": min_areas,
        "metrics": metrics,
        "latency_ms": latency_ms,
        "config": asdict(config),
    }
    (output_dir / "damage_segmentation_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    load_damage_segmentation_model(checkpoint_path, device="cpu")
    print(json.dumps({"event": "complete", "checkpoint": str(checkpoint_path), **report}), flush=True)
    return checkpoint_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/module_b"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--head-epochs", type=int, default=10)
    parser.add_argument("--finetune-epochs", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = DamageTrainConfig(batch_size=args.batch_size, workers=args.workers, head_epochs=args.head_epochs, finetune_epochs=args.finetune_epochs)
    train_damage_segmentation(args.manifest, args.output_dir, config, args.device)


if __name__ == "__main__":
    main()
