"""HITL polygon masks and paired transforms for damage segmentation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Sequence

from PIL import Image, ImageChops, ImageDraw, ImageOps

from .condition_dataset import ConditionManifest, ConditionSample, load_condition_manifest
from .dataset import load_rgb_image
from .model import DAMAGE_IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD


DAMAGE_PIXEL_CLASSES = ("background", "scratch", "collision_damage")
DAMAGE_CATEGORIES = ("scratch", "collision_damage")
HITL_CLASS_TO_PIXEL = {
    "Scratch": 1,
    "Dent": 2,
    "Cracked": 2,
    "Broken part": 2,
    "Missing part": 2,
}


@dataclass(frozen=True)
class DamageSegmentationSample:
    image_path: Path
    annotation_path: Path
    group_id: str
    source_id: str
    original_id: str
    labels: tuple[int, int]


def _annotation_path(sample: ConditionSample) -> Path:
    if sample.path.parent.name != "img":
        raise ValueError(f"Expected a Supervisely img directory: {sample.path}")
    return sample.path.parent.parent / "ann" / f"{sample.path.name}.json"


def _load_annotation(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read Supervisely annotation: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Annotation must be a JSON object: {path}")
    return value


def load_damage_samples(
    manifest_path: str | Path, *, validate_images: bool = True
) -> tuple[ConditionManifest, list[DamageSegmentationSample]]:
    """Load HITL damage samples without treating part polygons as negatives."""
    manifest = load_condition_manifest(manifest_path, validate_images=validate_images)
    samples: list[DamageSegmentationSample] = []
    for sample in manifest.samples:
        annotation_path = _annotation_path(sample)
        annotation = _load_annotation(annotation_path)
        objects = annotation.get("objects")
        if not isinstance(objects, list):
            raise ValueError(f"Annotation objects must be a list: {annotation_path}")
        present = {
            HITL_CLASS_TO_PIXEL[item.get("classTitle")]
            for item in objects
            if isinstance(item, dict) and item.get("classTitle") in HITL_CLASS_TO_PIXEL
        }
        samples.append(
            DamageSegmentationSample(
                image_path=sample.path,
                annotation_path=annotation_path,
                group_id=sample.group_id,
                source_id=sample.source_id,
                original_id=sample.original_id,
                labels=(int(1 in present), int(2 in present)),
            )
        )
    if not samples:
        raise ValueError("Damage segmentation dataset is empty")
    return manifest, samples


def _draw_polygon(binary: Image.Image, points: object, *, fill: int) -> None:
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("Polygon must contain at least three points")
    coordinates: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("Polygon coordinates must be [x, y] pairs")
        coordinates.append((float(point[0]), float(point[1])))
    ImageDraw.Draw(binary).polygon(coordinates, fill=fill)


def rasterize_damage_mask(annotation_path: str | Path, image_size: tuple[int, int]) -> Image.Image:
    """Rasterize supported polygons; collision pixels take precedence over scratches."""
    path = Path(annotation_path)
    annotation = _load_annotation(path)
    size = annotation.get("size")
    if not isinstance(size, dict) or (size.get("width"), size.get("height")) != image_size:
        raise ValueError(f"Annotation/image size mismatch: {path}")
    objects = annotation.get("objects")
    if not isinstance(objects, list):
        raise ValueError(f"Annotation objects must be a list: {path}")

    unions = {
        1: Image.new("1", image_size, 0),
        2: Image.new("1", image_size, 0),
    }
    for item in objects:
        if not isinstance(item, dict):
            raise ValueError(f"Annotation object must be a JSON object: {path}")
        pixel_class = HITL_CLASS_TO_PIXEL.get(item.get("classTitle"))
        if pixel_class is None:
            continue
        if item.get("geometryType") != "polygon":
            raise ValueError(f"Supported damage must use polygon geometry: {path}")
        points = item.get("points")
        if not isinstance(points, dict):
            raise ValueError(f"Polygon points must be an object: {path}")
        object_mask = Image.new("1", image_size, 0)
        _draw_polygon(object_mask, points.get("exterior"), fill=1)
        interiors = points.get("interior", [])
        if not isinstance(interiors, list):
            raise ValueError(f"Polygon interior must be a list: {path}")
        for interior in interiors:
            _draw_polygon(object_mask, interior, fill=0)
        unions[pixel_class] = ImageChops.lighter(unions[pixel_class], object_mask)

    mask = Image.new("L", image_size, 0)
    mask.paste(1, mask=unions[1])
    mask.paste(2, mask=unions[2])
    return mask


def resize_and_pad_pair(
    image: Image.Image, mask: Image.Image, size: int = DAMAGE_IMAGE_SIZE
) -> tuple[Image.Image, Image.Image]:
    if size <= 0:
        raise ValueError("size must be positive")
    resized, left, top = letterbox_geometry(image.size, size)
    image_canvas = Image.new("RGB", (size, size), (0, 0, 0))
    mask_canvas = Image.new("L", (size, size), 0)
    image_canvas.paste(image.resize(resized, Image.Resampling.BILINEAR), (left, top))
    mask_canvas.paste(mask.resize(resized, Image.Resampling.NEAREST), (left, top))
    return image_canvas, mask_canvas


def letterbox_geometry(
    original_size: tuple[int, int], size: int
) -> tuple[tuple[int, int], int, int]:
    """Return resized dimensions and top-left offset used by letterboxing."""
    if size <= 0:
        raise ValueError("size must be positive")
    width, height = original_size
    if width <= 0 or height <= 0:
        raise ValueError("original image dimensions must be positive")
    scale = min(size / width, size / height)
    resized = (max(1, round(width * scale)), max(1, round(height * scale)))
    return resized, (size - resized[0]) // 2, (size - resized[1]) // 2


def letterbox_content_mask(original_size: tuple[int, int], size: int):
    """Return a boolean array selecting real image pixels and excluding padding."""
    import numpy as np

    resized, left, top = letterbox_geometry(original_size, size)
    mask = np.zeros((size, size), dtype=bool)
    mask[top : top + resized[1], left : left + resized[0]] = True
    return mask


def split_damage_samples(
    samples: Sequence[DamageSegmentationSample], *, seed: int,
    validation_fraction: float = 0.2, test_fraction: float = 0.2,
    attempts: int = 10_000,
) -> tuple[list[DamageSegmentationSample], list[DamageSegmentationSample], list[DamageSegmentationSample]]:
    """Create a reproducible group split with positive and negative examples per class."""
    if validation_fraction <= 0 or test_fraction <= 0 or validation_fraction + test_fraction >= 1:
        raise ValueError("Split fractions must be positive and sum to less than one")
    groups: dict[str, list[DamageSegmentationSample]] = {}
    for sample in samples:
        groups.setdefault(sample.group_id, []).append(sample)
    group_ids = sorted(groups)
    if len(group_ids) < 3:
        raise ValueError("Damage dataset needs at least three independent groups")
    rng = random.Random(seed)
    val_count = max(1, round(len(group_ids) * validation_fraction))
    test_count = max(1, round(len(group_ids) * test_fraction))

    def complete(items: Sequence[DamageSegmentationSample]) -> bool:
        return bool(items) and all(
            any(sample.labels[index] == 1 for sample in items)
            and any(sample.labels[index] == 0 for sample in items)
            for index in range(len(DAMAGE_CATEGORIES))
        )

    for _ in range(attempts):
        shuffled = group_ids.copy()
        rng.shuffle(shuffled)
        test_groups = set(shuffled[:test_count])
        val_groups = set(shuffled[test_count:test_count + val_count])
        train_groups = set(shuffled[test_count + val_count:])
        train = [item for group in sorted(train_groups) for item in groups[group]]
        validation = [item for group in sorted(val_groups) for item in groups[group]]
        test = [item for group in sorted(test_groups) for item in groups[group]]
        if complete(train) and complete(validation) and complete(test):
            return train, validation, test
    raise ValueError("Unable to create complete damage train/validation/test splits")


class DamageSegmentationDataset:
    def __init__(self, samples: Sequence[DamageSegmentationSample], *, training: bool, image_size: int = DAMAGE_IMAGE_SIZE):
        self.samples = list(samples)
        self.training = training
        self.image_size = image_size

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        import numpy as np
        import torch
        from torchvision.transforms import functional as functional

        sample = self.samples[index]
        image = load_rgb_image(sample.image_path)
        mask = rasterize_damage_mask(sample.annotation_path, image.size)
        image, mask = resize_and_pad_pair(image, mask, self.image_size)
        if self.training and torch.rand(()) < 0.5:
            image = ImageOps.mirror(image)
            mask = ImageOps.mirror(mask)
        tensor = functional.to_tensor(image)
        tensor = functional.normalize(tensor, IMAGENET_MEAN, IMAGENET_STD)
        mask_tensor = torch.from_numpy(np.array(mask, dtype="int64"))
        return tensor, mask_tensor, index
