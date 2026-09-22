"""Jointly fine-tune the HITL segmenter and Hotai visible-damage gate."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import time
from typing import Sequence

import numpy as np

from .annotate_hotai import AnnotatedPhotoSample, load_annotated_samples
from .damage_inference import load_damage_segmentation_model
from .damage_segmentation import (
    DAMAGE_PIXEL_CLASSES,
    DamageSegmentationDataset,
    DamageSegmentationSample,
    load_damage_samples,
    split_damage_samples,
)
from .dataset import ClaimImageDataset
from .evaluate_hotai_claim_proxy import binary_metrics
from .model import (
    DEFAULT_IMAGE_SIZE,
    build_damage_segmentation_model,
    build_shared_visible_damage_head,
    build_transform,
    shared_visible_damage_logits,
)
from .train import resolve_device, set_seed, sigmoid
from .train_damage_calibrator import (
    select_recall_constrained_threshold,
    split_annotated_locked_test,
)
from .train_damage_segmentation import (
    DamageTrainConfig,
    calculate_class_weights,
    collect_probabilities,
    make_report,
)


MODEL_VERSION = "lraspp-mobilenetv3-large-hotai-multitask-v1"
GATE_ARCHITECTURE = "shared_lraspp_high_pool_linear"


@dataclass(frozen=True)
class MultitaskConfig:
    seed: int = 20260914
    gate_image_size: int = DEFAULT_IMAGE_SIZE
    gate_batch_size: int = 8
    segmentation_batch_size: int = 2
    workers: int = 0
    head_epochs: int = 12
    finetune_epochs: int = 24
    patience: int = 6
    head_learning_rate: float = 1e-3
    backbone_learning_rate: float = 1e-5
    gate_learning_rate: float = 1e-4
    segmentation_head_learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    segmentation_loss_weight: float = 0.5
    hotai_validation_fraction: float = 0.2
    hotai_test_fraction: float = 0.2
    minimum_validation_recall: float = 0.8
    minimum_locked_recall: float = 0.8
    minimum_locked_specificity: float = 0.5


def split_hotai_samples(samples: Sequence[AnnotatedPhotoSample], config: MultitaskConfig):
    development, locked_test = split_annotated_locked_test(
        samples, seed=config.seed, test_fraction=config.hotai_test_fraction
    )
    train, validation = split_annotated_locked_test(
        development,
        seed=config.seed + 1,
        test_fraction=config.hotai_validation_fraction,
    )
    partitions = (train, validation, locked_test)
    groups = [{sample.group_id for sample in part} for part in partitions]
    if not groups[0].isdisjoint(groups[1]) or not groups[0].isdisjoint(groups[2]) or not groups[1].isdisjoint(groups[2]):
        raise RuntimeError("Hotai vehicle group leaked across train/validation/test")
    return partitions


def make_balanced_gate_loader(samples, config: MultitaskConfig, *, training: bool, seed: int):
    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    dataset = ClaimImageDataset(
        samples,
        build_transform(training=training, image_size=config.gate_image_size),
    )
    generator = torch.Generator().manual_seed(seed)
    if training:
        labels = np.asarray([sample.label for sample in samples], dtype=np.int64)
        counts = np.bincount(labels, minlength=2)
        if np.any(counts == 0):
            raise ValueError("Balanced sampling requires both Hotai labels")
        weights = torch.tensor([1.0 / counts[label] for label in labels], dtype=torch.double)
        sample_count = int(2 * counts.max())
        sampler = WeightedRandomSampler(weights, sample_count, replacement=True, generator=generator)
        return DataLoader(
            dataset,
            batch_size=config.gate_batch_size,
            sampler=sampler,
            num_workers=config.workers,
            pin_memory=torch.cuda.is_available(),
        )
    return DataLoader(
        dataset,
        batch_size=config.gate_batch_size,
        shuffle=False,
        num_workers=config.workers,
        pin_memory=torch.cuda.is_available(),
    )


def make_segmentation_loader(samples, config: MultitaskConfig, *, training: bool, seed: int):
    import torch
    from torch.utils.data import DataLoader

    generator = torch.Generator().manual_seed(seed)
    return DataLoader(
        DamageSegmentationDataset(samples, training=training),
        batch_size=config.segmentation_batch_size,
        shuffle=training,
        num_workers=config.workers,
        pin_memory=torch.cuda.is_available(),
        generator=generator,
    )


def collect_gate_probabilities(model, gate_head, samples, config, device):
    import torch

    loader = make_balanced_gate_loader(
        samples, config, training=False, seed=config.seed
    )
    logits: list[float] = []
    labels: list[int] = []
    model.eval()
    gate_head.eval()
    with torch.inference_mode():
        for images, batch_labels, _ in loader:
            output = shared_visible_damage_logits(
                model, gate_head, images.to(device, non_blocking=True)
            )
            logits.extend(float(value) for value in output.detach().cpu())
            labels.extend(int(value) for value in batch_labels)
    return sigmoid(np.asarray(logits)), np.asarray(labels, dtype=np.int64)


def gate_metrics(probabilities, labels, threshold):
    predictions = (probabilities > threshold).astype(np.int64)
    report = binary_metrics(labels.tolist(), predictions.tolist())
    negatives = int(np.sum(labels == 0))
    report.update(
        {
            "threshold": float(threshold),
            "false_positive_rate": report["false_positive_count"] / negatives if negatives else 0.0,
            "sample_count": int(len(labels)),
            "positive_count": int(labels.sum()),
            "negative_count": negatives,
        }
    )
    return report


def _next_batch(iterator, loader):
    try:
        return next(iterator), iterator
    except StopIteration:
        iterator = iter(loader)
        return next(iterator), iterator


def _train_epoch(
    model,
    gate_head,
    gate_loader,
    segmentation_loader,
    gate_criterion,
    segmentation_criterion,
    optimizer,
    scaler,
    device,
    segmentation_weight: float,
    *,
    joint: bool,
):
    import torch

    model.train(joint)
    gate_head.train()
    if not joint:
        model.eval()
    # During the joint stage frozen weights stay frozen, while BatchNorm running
    # statistics adapt to the alternating HITL and Hotai domains.
    gate_total = 0.0
    segmentation_total = 0.0
    segmentation_iterator = iter(segmentation_loader)
    for images, labels, _ in gate_loader:
        optimizer.zero_grad(set_to_none=True)
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        with torch.amp.autocast(device_type=device.type, enabled=device.type == "cuda"):
            logits = shared_visible_damage_logits(model, gate_head, images)
            gate_loss = gate_criterion(logits, labels)
        scaler.scale(gate_loss).backward()
        segmentation_loss_value = 0.0
        if joint:
            (seg_images, masks, _), segmentation_iterator = _next_batch(
                segmentation_iterator, segmentation_loader
            )
            seg_images = seg_images.to(device, non_blocking=True)
            masks = masks.to(device, non_blocking=True)
            with torch.amp.autocast(device_type=device.type, enabled=device.type == "cuda"):
                segmentation_loss = segmentation_criterion(model(seg_images)["out"], masks)
            scaler.scale(segmentation_weight * segmentation_loss).backward()
            segmentation_loss_value = float(segmentation_loss.item())
        scaler.step(optimizer)
        scaler.update()
        gate_total += float(gate_loss.item())
        segmentation_total += segmentation_loss_value
    count = max(1, len(gate_loader))
    return gate_total / count, segmentation_total / count


def _configure_head_stage(model, gate_head):
    for parameter in model.parameters():
        parameter.requires_grad = False
    for parameter in gate_head.parameters():
        parameter.requires_grad = True


def _configure_joint_stage(model, gate_head, blocks_to_unfreeze: int = 3):
    for parameter in model.parameters():
        parameter.requires_grad = False
    blocks = list(model.backbone.children())
    for block in blocks[-blocks_to_unfreeze:]:
        for parameter in block.parameters():
            parameter.requires_grad = True
    for parameter in model.classifier.parameters():
        parameter.requires_grad = True
    for parameter in gate_head.parameters():
        parameter.requires_grad = True
    return blocks[-blocks_to_unfreeze:]


def _fit_stage(
    model,
    gate_head,
    hotai_train,
    hotai_validation,
    hitl_train,
    segmentation_criterion,
    config,
    device,
    *,
    stage: str,
    epochs: int,
):
    import torch

    joint = stage == "joint"
    if joint:
        backbone_blocks = _configure_joint_stage(model, gate_head)
        optimizer = torch.optim.AdamW(
            [
                {"params": [p for block in backbone_blocks for p in block.parameters()], "lr": config.backbone_learning_rate},
                {"params": model.classifier.parameters(), "lr": config.segmentation_head_learning_rate},
                {"params": gate_head.parameters(), "lr": config.gate_learning_rate},
            ],
            weight_decay=config.weight_decay,
        )
    else:
        _configure_head_stage(model, gate_head)
        optimizer = torch.optim.AdamW(
            gate_head.parameters(),
            lr=config.head_learning_rate,
            weight_decay=config.weight_decay,
        )
    gate_loader = make_balanced_gate_loader(
        hotai_train, config, training=True, seed=config.seed + (1 if joint else 0)
    )
    segmentation_loader = make_segmentation_loader(
        hitl_train, config, training=True, seed=config.seed
    )
    gate_criterion = torch.nn.BCEWithLogitsLoss()
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best_state = (deepcopy(model.state_dict()), deepcopy(gate_head.state_dict()))
    best_key = (-math.inf, -math.inf, -math.inf)
    best_threshold = 0.5
    best_epoch = 0
    stale = 0
    for epoch in range(1, epochs + 1):
        gate_loss, segmentation_loss = _train_epoch(
            model,
            gate_head,
            gate_loader,
            segmentation_loader,
            gate_criterion,
            segmentation_criterion,
            optimizer,
            scaler,
            device,
            config.segmentation_loss_weight,
            joint=joint,
        )
        probabilities, labels = collect_gate_probabilities(
            model, gate_head, hotai_validation, config, device
        )
        threshold, metrics = select_recall_constrained_threshold(
            probabilities, labels, config.minimum_validation_recall
        )
        key = (
            float(metrics["balanced_accuracy"]),
            float(metrics["specificity"]),
            float(metrics["recall"]),
        )
        print(json.dumps({"event": "epoch", "stage": stage, "epoch": epoch, "gate_loss": gate_loss, "segmentation_loss": segmentation_loss, "threshold": threshold, **metrics}), flush=True)
        if key > best_key:
            best_key = key
            best_threshold = threshold
            best_epoch = epoch
            best_state = (deepcopy(model.state_dict()), deepcopy(gate_head.state_dict()))
            stale = 0
        else:
            stale += 1
            if stale >= config.patience:
                break
    model.load_state_dict(best_state[0])
    gate_head.load_state_dict(best_state[1])
    return best_epoch, best_threshold


def train_multitask_damage(
    manifest_path: Path,
    queue_path: Path,
    annotations_path: Path,
    base_checkpoint_path: Path,
    output_dir: Path,
    config: MultitaskConfig,
    device_name: str,
) -> Path:
    import torch

    set_seed(config.seed)
    device = resolve_device(device_name)
    manifest, hitl_samples = load_damage_samples(manifest_path)
    hitl_train, hitl_validation, hitl_test = split_damage_samples(
        hitl_samples, seed=config.seed
    )
    hotai_samples = load_annotated_samples(queue_path, annotations_path)
    hotai_train, hotai_validation, hotai_test = split_hotai_samples(hotai_samples, config)
    base = torch.load(base_checkpoint_path, map_location="cpu", weights_only=True)
    model = build_damage_segmentation_model(pretrained_backbone=False)
    model.load_state_dict(base["model_state_dict"])
    model.to(device)
    gate_head = build_shared_visible_damage_head().to(device)

    segmentation_config = DamageTrainConfig(
        batch_size=config.segmentation_batch_size, workers=config.workers
    )
    class_weights = calculate_class_weights(hitl_train, segmentation_config, device)
    segmentation_criterion = torch.nn.CrossEntropyLoss(weight=class_weights)
    started = time.perf_counter()
    head_epoch, _ = _fit_stage(
        model, gate_head, hotai_train, hotai_validation, hitl_train,
        segmentation_criterion, config, device, stage="head", epochs=config.head_epochs,
    )
    joint_epoch, threshold = _fit_stage(
        model, gate_head, hotai_train, hotai_validation, hitl_train,
        segmentation_criterion, config, device, stage="joint", epochs=config.finetune_epochs,
    )
    validation_probabilities, validation_labels = collect_gate_probabilities(
        model, gate_head, hotai_validation, config, device
    )
    locked_probabilities, locked_labels = collect_gate_probabilities(
        model, gate_head, hotai_test, config, device
    )
    validation_report = gate_metrics(validation_probabilities, validation_labels, threshold)
    locked_report = gate_metrics(locked_probabilities, locked_labels, threshold)

    thresholds = {key: float(value) for key, value in base["probability_thresholds"].items()}
    areas = {key: int(value) for key, value in base["min_area_pixels"].items()}
    hitl_probabilities, hitl_labels, hitl_confusion = collect_probabilities(
        model, hitl_test, segmentation_config, device
    )
    hitl_report = make_report(
        hitl_probabilities, hitl_labels, hitl_confusion, thresholds, areas
    )
    report = {
        "status": "experimental_review_only",
        "model_version": MODEL_VERSION,
        "device": str(device),
        "elapsed_seconds": time.perf_counter() - started,
        "hotai_dataset": {
            "total": len(hotai_samples), "train": len(hotai_train),
            "validation": len(hotai_validation), "locked_test": len(hotai_test),
        },
        "hitl_dataset": {
            "total": len(hitl_samples), "train": len(hitl_train),
            "validation": len(hitl_validation), "locked_test": len(hitl_test),
        },
        "selected_epochs": {"head": head_epoch, "joint": joint_epoch},
        "gate": {"validation": validation_report, "locked_test": locked_report},
        "hitl_segmentation_locked_test": hitl_report,
        "config": asdict(config),
    }
    passed = (
        locked_report["recall"] >= config.minimum_locked_recall
        and locked_report["specificity"] >= config.minimum_locked_specificity
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "multitask_damage_metrics.json"
    if not passed:
        report["status"] = "quality_gate_failed"
        report["reason"] = "Locked Hotai recall/specificity requirements were not both satisfied"
        metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError(report["reason"])

    checkpoint_path = output_dir / "damage_multitask.pth"
    checkpoint = deepcopy(base)
    checkpoint["model_state_dict"] = {
        key: value.detach().cpu() for key, value in model.state_dict().items()
    }
    checkpoint["model_version"] = MODEL_VERSION
    checkpoint["shared_visible_damage_gate"] = {
        "architecture": GATE_ARCHITECTURE,
        "model_state_dict": {
            key: value.detach().cpu() for key, value in gate_head.state_dict().items()
        },
        "image_size": config.gate_image_size,
        "threshold": float(threshold),
        "label_mapping": {"no_detected_damage": 0, "damage_detected": 1},
    }
    checkpoint["multitask_training"] = {
        "hotai_label_source": "manual_visible_damage",
        "hitl_manifest_sha256": manifest.sha256,
        "gate_validation": validation_report,
        "gate_locked_test": locked_report,
    }
    torch.save(checkpoint, checkpoint_path)
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    load_damage_segmentation_model(checkpoint_path, device="cpu")
    print(json.dumps({"event": "complete", "checkpoint": str(checkpoint_path), **report}), flush=True)
    return checkpoint_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/condition_manifest.hitl-only.json"))
    parser.add_argument("--queue", type=Path, default=Path("data/hotai_annotation_queue.json"))
    parser.add_argument("--annotations", type=Path, default=Path("data/hotai_annotations.json"))
    parser.add_argument("--base-checkpoint", type=Path, default=Path("artifacts/module_b/damage_segmenter.pth"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/module_b"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--head-epochs", type=int, default=12)
    parser.add_argument("--finetune-epochs", type=int, default=24)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--gate-batch-size", type=int, default=8)
    parser.add_argument("--segmentation-batch-size", type=int, default=2)
    parser.add_argument("--minimum-validation-recall", type=float, default=0.8)
    parser.add_argument("--minimum-locked-recall", type=float, default=0.8)
    parser.add_argument("--minimum-locked-specificity", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = MultitaskConfig(
        head_epochs=args.head_epochs,
        finetune_epochs=args.finetune_epochs,
        workers=args.workers,
        gate_batch_size=args.gate_batch_size,
        segmentation_batch_size=args.segmentation_batch_size,
        minimum_validation_recall=args.minimum_validation_recall,
        minimum_locked_recall=args.minimum_locked_recall,
        minimum_locked_specificity=args.minimum_locked_specificity,
    )
    train_multitask_damage(
        args.manifest,
        args.queue,
        args.annotations,
        args.base_checkpoint,
        args.output_dir,
        config,
        args.device,
    )


if __name__ == "__main__":
    main()
