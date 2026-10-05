"""Fine-tune LR-ASPP MobileNetV3-Large on MoLa-VI stain/dirt masks."""

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

from .cleanliness_dataset import (
    CLEANLINESS_CATEGORIES,
    CLEANLINESS_PIXEL_CLASSES,
    CleanlinessSegmentationDataset,
    CleanlinessSegmentationSample,
    dataset_manifest_sha256,
    discover_mola_vi_samples,
    load_cleanliness_mask,
    split_cleanliness_samples,
)
from .cleanliness_inference import CLEANLINESS_TASK_NAME, load_cleanliness_model
from .condition_schema import REVIEW_STATE
from .model import (
    CLEANLINESS_IMAGE_SIZE,
    CLEANLINESS_SEGMENTATION_ARCHITECTURE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_cleanliness_segmentation_model,
    freeze_damage_backbone,
    unfreeze_last_damage_blocks,
)
from .train import resolve_device, set_seed


DEFAULT_SEED = 20260914
MODEL_VERSION = "lraspp-mobilenetv3-large-interior-cleanliness-v1"


@dataclass(frozen=True)
class CleanlinessTrainConfig:
    seed: int = DEFAULT_SEED
    image_size: int = CLEANLINESS_IMAGE_SIZE
    batch_size: int = 4
    workers: int = 0
    head_epochs: int = 10
    finetune_epochs: int = 30
    patience: int = 7
    head_learning_rate: float = 1e-3
    backbone_learning_rate: float = 1e-5
    finetune_head_learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    dice_weight: float = 0.5
    validation_fraction: float = 0.2
    test_fraction: float = 0.2
    threshold_candidates: tuple[float, ...] = tuple(float(x) for x in np.linspace(0.1, 0.9, 17))
    area_candidates: tuple[int, ...] = (16, 64, 256, 1024)


class WeightedCrossEntropyDiceLoss:
    def __init__(self, class_weights, *, dice_weight: float) -> None:
        import torch

        self.cross_entropy = torch.nn.CrossEntropyLoss(weight=class_weights)
        self.dice_weight = dice_weight

    def __call__(self, logits, targets):
        import torch
        from torch.nn import functional

        ce = self.cross_entropy(logits, targets)
        probabilities = torch.softmax(logits, dim=1)
        one_hot = functional.one_hot(targets, num_classes=len(CLEANLINESS_PIXEL_CLASSES))
        one_hot = one_hot.permute(0, 3, 1, 2).to(probabilities.dtype)
        dims = (0, 2, 3)
        intersection = (probabilities * one_hot).sum(dims)
        denominator = probabilities.sum(dims) + one_hot.sum(dims)
        dice = (2 * intersection + 1.0) / (denominator + 1.0)
        foreground_dice_loss = 1.0 - dice[1:].mean()
        return ce + self.dice_weight * foreground_dice_loss


def make_loader(
    samples: Sequence[CleanlinessSegmentationSample],
    *,
    training: bool,
    config: CleanlinessTrainConfig,
    seed: int,
):
    import torch
    from torch.utils.data import DataLoader

    generator = torch.Generator().manual_seed(seed)
    return DataLoader(
        CleanlinessSegmentationDataset(
            samples, training=training, image_size=config.image_size
        ),
        batch_size=config.batch_size,
        shuffle=training,
        num_workers=config.workers,
        pin_memory=torch.cuda.is_available(),
        generator=generator,
    )


def calculate_class_weights(samples, config, device):
    import torch
    from PIL import Image

    from .damage_segmentation import letterbox_geometry

    counts = torch.zeros(len(CLEANLINESS_PIXEL_CLASSES), dtype=torch.float64)
    for sample in samples:
        mask, _ = load_cleanliness_mask(sample.mask_path)
        resized, left, top = letterbox_geometry(mask.size, config.image_size)
        canvas = Image.new("L", (config.image_size, config.image_size), 0)
        canvas.paste(mask.resize(resized, Image.Resampling.NEAREST), (left, top))
        values = torch.from_numpy(np.asarray(canvas, dtype=np.int64).copy())
        counts += torch.bincount(values.reshape(-1), minlength=len(CLEANLINESS_PIXEL_CLASSES))
    if torch.any(counts == 0):
        missing = [CLEANLINESS_PIXEL_CLASSES[i] for i, value in enumerate(counts) if value == 0]
        raise ValueError(f"Training split has no pixels for: {missing}")
    frequencies = counts / counts.sum()
    weights = torch.rsqrt(frequencies)
    return (weights / weights.mean()).clamp(max=20.0).to(device=device, dtype=torch.float32)


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
                loss = criterion(model(images)["out"], masks)
            if training:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            total_loss += float(loss.item()) * len(images)
            total_items += len(images)
    return total_loss / total_items


def _fit_stage(
    model,
    train_samples,
    validation_samples,
    criterion,
    optimizer,
    *,
    epochs,
    config,
    device,
    seed,
    stage,
    frozen_blocks,
):
    import torch

    train_loader = make_loader(train_samples, training=True, config=config, seed=seed)
    validation_loader = make_loader(validation_samples, training=False, config=config, seed=seed)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best_state = deepcopy(model.state_dict())
    best_loss = math.inf
    best_epoch = 0
    stale = 0
    for epoch in range(1, epochs + 1):
        train_loss = _run_epoch(
            model, train_loader, criterion, device, optimizer, scaler, frozen_blocks
        )
        validation_loss = _run_epoch(model, validation_loader, criterion, device)
        print(
            json.dumps(
                {
                    "event": "epoch",
                    "stage": stage,
                    "epoch": epoch,
                    "train_loss": train_loss,
                    "validation_loss": validation_loss,
                }
            ),
            flush=True,
        )
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
    model = build_cleanliness_segmentation_model(pretrained_backbone=True).to(device)
    class_weights = calculate_class_weights(train_samples, config, device)
    criterion = WeightedCrossEntropyDiceLoss(class_weights, dice_weight=config.dice_weight)
    freeze_damage_backbone(model)
    optimizer = torch.optim.AdamW(
        model.classifier.parameters(),
        lr=config.head_learning_rate,
        weight_decay=config.weight_decay,
    )
    head_epoch, _ = _fit_stage(
        model,
        train_samples,
        validation_samples,
        criterion,
        optimizer,
        epochs=config.head_epochs,
        config=config,
        device=device,
        seed=config.seed,
        stage="head",
        frozen_blocks=len(list(model.backbone.children())),
    )
    unfreeze_last_damage_blocks(model, 3)
    blocks = list(model.backbone.children())
    optimizer = torch.optim.AdamW(
        [
            {
                "params": [parameter for block in blocks[-3:] for parameter in block.parameters()],
                "lr": config.backbone_learning_rate,
            },
            {
                "params": model.classifier.parameters(),
                "lr": config.finetune_head_learning_rate,
            },
        ],
        weight_decay=config.weight_decay,
    )
    finetune_epoch, _ = _fit_stage(
        model,
        train_samples,
        validation_samples,
        criterion,
        optimizer,
        epochs=config.finetune_epochs,
        config=config,
        device=device,
        seed=config.seed + 1,
        stage="finetune",
        frozen_blocks=max(0, len(blocks) - 3),
    )
    return model.eval(), class_weights.detach().cpu().tolist(), head_epoch, finetune_epoch


def _binary_metrics(predictions: np.ndarray, labels: np.ndarray):
    tp = int(np.sum(predictions & (labels == 1)))
    tn = int(np.sum(~predictions & (labels == 0)))
    fp = int(np.sum(predictions & (labels == 0)))
    fn = int(np.sum(~predictions & (labels == 1)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f2 = 5 * precision * recall / (4 * precision + recall) if precision + recall else 0.0
    return {
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f2": f2,
        "false_negative_count": fn,
        "false_positive_count": fp,
    }


def collect_summary(model, samples, config, device):
    import torch

    loader = make_loader(samples, training=False, config=config, seed=config.seed)
    thresholds = np.asarray(config.threshold_candidates, dtype=np.float32)
    counts = np.zeros((len(samples), 2, len(thresholds)), dtype=np.int64)
    labels = np.asarray([sample.labels for sample in samples], dtype=np.int64)
    confusion = np.zeros((3, 3), dtype=np.int64)
    model.eval()
    with torch.inference_mode():
        for images, masks, indices in loader:
            logits = model(images.to(device, non_blocking=True))["out"]
            probabilities = torch.softmax(logits, dim=1).cpu().numpy()
            predictions = logits.argmax(dim=1).cpu().numpy()
            targets = masks.numpy()
            for truth, predicted in zip(targets, predictions, strict=True):
                confusion += np.bincount(
                    truth.reshape(-1) * 3 + predicted.reshape(-1), minlength=9
                ).reshape(3, 3)
            for batch_index, sample_index in enumerate(indices.tolist()):
                for category_index in range(2):
                    values = probabilities[batch_index, category_index + 1]
                    counts[sample_index, category_index] = np.asarray(
                        [(values > threshold).sum() for threshold in thresholds]
                    )
    return counts, labels, confusion


def select_detection_gates(counts, labels, config):
    thresholds: dict[str, float] = {}
    min_areas: dict[str, int] = {}
    for category_index, category in enumerate(CLEANLINESS_CATEGORIES):
        best_key = (-1.0, -1.0, -1.0, 0.0, 0)
        best = (0.5, 64)
        for threshold_index, threshold in enumerate(config.threshold_candidates):
            for area in config.area_candidates:
                metrics = _binary_metrics(
                    counts[:, category_index, threshold_index] >= area,
                    labels[:, category_index],
                )
                key = (
                    metrics["f2"],
                    metrics["recall"],
                    metrics["precision"],
                    threshold,
                    -area,
                )
                if key > best_key:
                    best_key = key
                    best = (threshold, area)
        thresholds[category], min_areas[category] = best
    return thresholds, min_areas


def report_from_summary(counts, labels, confusion, thresholds, min_areas, config):
    categories = {}
    for category_index, category in enumerate(CLEANLINESS_CATEGORIES):
        threshold_index = config.threshold_candidates.index(thresholds[category])
        categories[category] = _binary_metrics(
            counts[:, category_index, threshold_index] >= min_areas[category],
            labels[:, category_index],
        )
        denominator = confusion[category_index + 1].sum()
        categories[category]["pixel_iou"] = (
            float(confusion[category_index + 1, category_index + 1])
            / float(
                denominator
                + confusion[:, category_index + 1].sum()
                - confusion[category_index + 1, category_index + 1]
            )
            if denominator
            else 0.0
        )
    return {"categories": categories, "pixel_confusion_matrix": confusion.tolist()}


def train_and_save(data_root: Path, output_dir: Path, config: CleanlinessTrainConfig, device_name: str):
    import torch

    started = time.perf_counter()
    samples = discover_mola_vi_samples(data_root, validate_images=False)
    train_samples, validation_samples, test_samples = split_cleanliness_samples(
        samples,
        seed=config.seed,
        validation_fraction=config.validation_fraction,
        test_fraction=config.test_fraction,
    )
    groups = [{sample.group_id for sample in part} for part in (train_samples, validation_samples, test_samples)]
    if not groups[0].isdisjoint(groups[1]) or not groups[0].isdisjoint(groups[2]) or not groups[1].isdisjoint(groups[2]):
        raise RuntimeError("MoLa-VI vehicle group leaked across train/validation/test")
    device = resolve_device(device_name)
    model, class_weights, head_epoch, finetune_epoch = fit_model(
        train_samples, validation_samples, config, device
    )
    validation_summary = collect_summary(model, validation_samples, config, device)
    thresholds, min_areas = select_detection_gates(
        validation_summary[0], validation_summary[1], config
    )
    validation_report = report_from_summary(
        *validation_summary, thresholds, min_areas, config
    )
    test_summary = collect_summary(model, test_samples, config, device)
    locked_report = report_from_summary(*test_summary, thresholds, min_areas, config)
    manifest_hash = dataset_manifest_sha256(samples)

    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "interior_cleanliness.pth"
    checkpoint = {
        "architecture": CLEANLINESS_SEGMENTATION_ARCHITECTURE,
        "task": CLEANLINESS_TASK_NAME,
        "status": "external_only_review_only",
        "review_state": REVIEW_STATE,
        "model_version": MODEL_VERSION,
        "model_state_dict": model.state_dict(),
        "pixel_classes": CLEANLINESS_PIXEL_CLASSES,
        "probability_thresholds": thresholds,
        "min_area_pixels": min_areas,
        "image_size": config.image_size,
        "normalization": {"mean": IMAGENET_MEAN, "std": IMAGENET_STD},
        "dataset_manifest_sha256": manifest_hash,
        "dataset": {"name": "MoLa-VI", "doi": "10.17632/cfsr5kvry3.1", "license": "CC BY 4.0"},
        "seed": config.seed,
        "config": asdict(config),
        "split_counts": {
            "all": len(samples),
            "train": len(train_samples),
            "validation": len(validation_samples),
            "locked_test": len(test_samples),
        },
        "class_weights": class_weights,
        "selected_epochs": {"head": head_epoch, "finetune": finetune_epoch},
        "validation_metrics": validation_report,
        "locked_test_metrics": locked_report,
    }
    torch.save(checkpoint, checkpoint_path)
    load_cleanliness_model(checkpoint_path, device="cpu")
    metrics = {
        "checkpoint": str(checkpoint_path),
        "status": checkpoint["status"],
        "model_version": MODEL_VERSION,
        "manifest_sha256": manifest_hash,
        "split_counts": checkpoint["split_counts"],
        "probability_thresholds": thresholds,
        "min_area_pixels": min_areas,
        "selected_epochs": checkpoint["selected_epochs"],
        "validation": validation_report,
        "locked_test": locked_report,
        "elapsed_seconds": time.perf_counter() - started,
    }
    metrics_path = output_dir / "interior_cleanliness_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics), flush=True)
    return checkpoint_path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/module_b"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--head-epochs", type=int, default=10)
    parser.add_argument("--finetune-epochs", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = CleanlinessTrainConfig(
        batch_size=args.batch_size,
        workers=args.workers,
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
    )
    train_and_save(args.data_root, args.output_dir, config, args.device)


if __name__ == "__main__":
    main()
