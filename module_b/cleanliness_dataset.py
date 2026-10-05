"""MoLa-VI image/mask discovery and paired transforms for cleanliness."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
from typing import Sequence

from PIL import Image, ImageOps

from .damage_segmentation import resize_and_pad_pair
from .dataset import load_rgb_image
from .model import CLEANLINESS_IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD


MOLA_STAIN_ID = 4
MOLA_DIRT_ID = 5
CLEANLINESS_PIXEL_CLASSES = ("background", "stain", "dirt")
CLEANLINESS_CATEGORIES = ("stain", "dirt")


@dataclass(frozen=True)
class CleanlinessSegmentationSample:
    image_path: Path
    mask_path: Path
    vehicle_id: str
    view: str
    original_id: str
    labels: tuple[int, int]

    @property
    def group_id(self) -> str:
        return self.vehicle_id


def _load_dataset_json(dataset_root: Path) -> dict[str, object]:
    path = dataset_root / "dataset.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read MoLa-VI dataset.json: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("MoLa-VI dataset.json must contain one JSON object")
    return value


def load_cleanliness_mask(mask_path: str | Path, expected_size: tuple[int, int] | None = None):
    import numpy as np

    path = Path(mask_path)
    try:
        with Image.open(path) as opened:
            mask = opened.convert("L")
    except OSError as exc:
        raise ValueError(f"Unable to decode MoLa-VI mask: {path}") from exc
    if expected_size is not None and mask.size != expected_size:
        raise ValueError(f"MoLa-VI image/mask size mismatch: {path}")
    raw = np.asarray(mask, dtype=np.uint8)
    if raw.size == 0 or int(raw.max()) > 6:
        raise ValueError(f"MoLa-VI mask contains unsupported pixel IDs: {path}")
    mapped = np.zeros(raw.shape, dtype=np.uint8)
    mapped[raw == MOLA_STAIN_ID] = 1
    mapped[raw == MOLA_DIRT_ID] = 2
    return Image.fromarray(mapped, mode="L"), (
        int(np.any(mapped == 1)),
        int(np.any(mapped == 2)),
    )


def discover_mola_vi_samples(
    dataset_root: str | Path, *, validate_images: bool = True
) -> list[CleanlinessSegmentationSample]:
    root = Path(dataset_root)
    if not root.is_dir():
        raise ValueError(f"MoLa-VI root does not exist: {root}")
    metadata = _load_dataset_json(root)
    cars = metadata.get("Cars")
    if not isinstance(cars, list):
        raise ValueError("MoLa-VI dataset.json is missing Cars")

    samples: list[CleanlinessSegmentationSample] = []
    for car in cars:
        if not isinstance(car, dict):
            raise ValueError("MoLa-VI Cars entries must be objects")
        vehicle_id = car.get("FullName")
        views = car.get("Images")
        if not isinstance(vehicle_id, str) or not vehicle_id.strip():
            raise ValueError("MoLa-VI car is missing FullName")
        if not isinstance(views, list):
            raise ValueError(f"MoLa-VI car {vehicle_id} is missing Images")
        for view_data in views:
            if not isinstance(view_data, dict):
                raise ValueError("MoLa-VI view entries must be objects")
            view = view_data.get("View")
            files = view_data.get("Files")
            segmentations = view_data.get("Segmentations")
            if not isinstance(view, str) or not isinstance(files, list) or not isinstance(segmentations, list):
                raise ValueError(f"MoLa-VI view metadata is invalid for {vehicle_id}")
            if len(files) != len(segmentations):
                raise ValueError(f"MoLa-VI image/mask counts differ for {vehicle_id}/{view}")
            for filename, segmentation_name in zip(files, segmentations, strict=True):
                if not isinstance(filename, str) or not isinstance(segmentation_name, str):
                    raise ValueError("MoLa-VI filenames must be strings")
                image_path = root / "IMAGES" / vehicle_id / view / filename
                mask_path = root / "SEGMENTATIONS" / vehicle_id / view / segmentation_name
                if not image_path.is_file() or not mask_path.is_file():
                    raise ValueError(f"Missing MoLa-VI pair: {vehicle_id}/{view}/{filename}")
                if validate_images:
                    image = load_rgb_image(image_path)
                    _, labels = load_cleanliness_mask(mask_path, image.size)
                else:
                    _, labels = load_cleanliness_mask(mask_path)
                samples.append(
                    CleanlinessSegmentationSample(
                        image_path=image_path,
                        mask_path=mask_path,
                        vehicle_id=vehicle_id,
                        view=view,
                        original_id=f"{vehicle_id}/{view}/{filename}",
                        labels=labels,
                    )
                )
    if not samples:
        raise ValueError("MoLa-VI contains no paired image/mask samples")
    return samples


def split_cleanliness_samples(
    samples: Sequence[CleanlinessSegmentationSample],
    *,
    seed: int,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
    attempts: int = 10_000,
) -> tuple[
    list[CleanlinessSegmentationSample],
    list[CleanlinessSegmentationSample],
    list[CleanlinessSegmentationSample],
]:
    if validation_fraction <= 0 or test_fraction <= 0 or validation_fraction + test_fraction >= 1:
        raise ValueError("Split fractions must be positive and sum to less than one")
    groups: dict[str, list[CleanlinessSegmentationSample]] = {}
    for sample in samples:
        groups.setdefault(sample.group_id, []).append(sample)
    group_ids = sorted(groups)
    if len(group_ids) < 3:
        raise ValueError("Cleanliness dataset needs at least three vehicle groups")
    validation_count = max(1, round(len(group_ids) * validation_fraction))
    test_count = max(1, round(len(group_ids) * test_fraction))
    rng = random.Random(seed)

    def complete(items: Sequence[CleanlinessSegmentationSample]) -> bool:
        return bool(items) and all(
            any(sample.labels[index] for sample in items)
            and any(not sample.labels[index] for sample in items)
            for index in range(2)
        )

    for _ in range(attempts):
        shuffled = group_ids.copy()
        rng.shuffle(shuffled)
        test_groups = set(shuffled[:test_count])
        validation_groups = set(shuffled[test_count : test_count + validation_count])
        train_groups = set(shuffled[test_count + validation_count :])
        train = [sample for group in sorted(train_groups) for sample in groups[group]]
        validation = [sample for group in sorted(validation_groups) for sample in groups[group]]
        test = [sample for group in sorted(test_groups) for sample in groups[group]]
        if complete(train) and complete(validation) and complete(test):
            return train, validation, test
    raise ValueError("Unable to create complete vehicle-grouped cleanliness splits")


def dataset_manifest_sha256(samples: Sequence[CleanlinessSegmentationSample]) -> str:
    payload = [
        {
            "id": sample.original_id,
            "vehicle_id": sample.vehicle_id,
            "labels": list(sample.labels),
        }
        for sample in sorted(samples, key=lambda item: item.original_id)
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CleanlinessSegmentationDataset:
    def __init__(
        self,
        samples: Sequence[CleanlinessSegmentationSample],
        *,
        training: bool,
        image_size: int = CLEANLINESS_IMAGE_SIZE,
    ) -> None:
        self.samples = list(samples)
        self.training = training
        self.image_size = image_size

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        import numpy as np
        import torch
        from torchvision.transforms import ColorJitter
        from torchvision.transforms import functional as functional
        from torchvision.transforms.functional import InterpolationMode

        sample = self.samples[index]
        image = load_rgb_image(sample.image_path)
        mask, _ = load_cleanliness_mask(sample.mask_path, image.size)
        image, mask = resize_and_pad_pair(image, mask, self.image_size)
        if self.training:
            if torch.rand(()) < 0.5:
                image = ImageOps.mirror(image)
                mask = ImageOps.mirror(mask)
            angle = float(torch.empty(1).uniform_(-5.0, 5.0))
            translate_limit = round(self.image_size * 0.02)
            translate = [
                int(torch.randint(-translate_limit, translate_limit + 1, (1,))),
                int(torch.randint(-translate_limit, translate_limit + 1, (1,))),
            ]
            scale = float(torch.empty(1).uniform_(0.95, 1.05))
            image = functional.affine(
                image,
                angle,
                translate,
                scale,
                0.0,
                interpolation=InterpolationMode.BILINEAR,
                fill=(0, 0, 0),
            )
            mask = functional.affine(
                mask,
                angle,
                translate,
                scale,
                0.0,
                interpolation=InterpolationMode.NEAREST,
                fill=0,
            )
            image = ColorJitter(
                brightness=0.1,
                contrast=0.1,
                saturation=0.05,
            )(image)
        tensor = functional.normalize(functional.to_tensor(image), IMAGENET_MEAN, IMAGENET_STD)
        mask_tensor = torch.from_numpy(np.asarray(mask, dtype=np.int64).copy())
        return tensor, mask_tensor, index
