"""Private dataset discovery and image preprocessing for Module B."""

from dataclasses import dataclass
from pathlib import Path
import random
import re
from typing import Callable, Sequence

from PIL import Image, ImageOps, UnidentifiedImageError


NEGATIVE_CLASS_DIR = "沒有進行索賠"
POSITIVE_CLASS_DIR = "進行索賠資料"
SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg", ".jfif"})
PLATE_PATTERN = re.compile(r"^([A-Za-z]{3}-?\d{4})")


class ImageDecodeError(ValueError):
    """Raised when a source image is not a valid supported JPEG image."""


@dataclass(frozen=True)
class ImageSample:
    path: Path
    label: int
    group_id: str

    def __post_init__(self) -> None:
        if self.label not in {0, 1}:
            raise ValueError("label must be 0 or 1")
        if not self.group_id:
            raise ValueError("group_id must be nonempty")


def extract_vehicle_group(filename: str) -> str:
    match = PLATE_PATTERN.match(Path(filename).stem.strip())
    if match is None:
        raise ValueError(f"Cannot extract vehicle group from filename: {filename!r}")
    return match.group(1).replace("-", "").upper()


def discover_samples(data_root: str | Path, *, validate_images: bool = True) -> list[ImageSample]:
    root = Path(data_root)
    if not root.is_dir():
        raise ValueError(f"Dataset root does not exist: {root}")

    samples: list[ImageSample] = []
    for directory_name, label in ((NEGATIVE_CLASS_DIR, 0), (POSITIVE_CLASS_DIR, 1)):
        directory = root / directory_name
        if not directory.is_dir():
            raise ValueError(f"Missing class directory: {directory}")
        class_samples: list[ImageSample] = []
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if validate_images:
                validate_jpeg(path)
            class_samples.append(
                ImageSample(path=path, label=label, group_id=extract_vehicle_group(path.name))
            )
        if not class_samples:
            raise ValueError(f"No supported images found in class directory: {directory}")
        samples.extend(class_samples)
    return samples


def validate_jpeg(path: str | Path) -> None:
    try:
        with Image.open(path, formats=("JPEG",)) as image:
            image.verify()
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        raise ImageDecodeError(f"Invalid JPEG/JFIF image: {path}") from exc


def load_rgb_image(source: str | Path | Image.Image) -> Image.Image:
    try:
        if isinstance(source, Image.Image):
            image = source.copy()
        else:
            # File suffixes are validated by the caller.  Let Pillow identify the
            # encoded format so condition training can also consume the PNG files
            # shipped in the official HITL archive.
            with Image.open(source) as opened:
                image = opened.copy()
        return ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        raise ImageDecodeError(f"Unable to decode image: {source}") from exc


def split_locked_test(
    samples: Sequence[ImageSample], *, seed: int, test_fraction: float = 0.2
) -> tuple[list[ImageSample], list[ImageSample]]:
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be within (0, 1)")
    group_labels: dict[str, int] = {}
    for sample in samples:
        previous = group_labels.setdefault(sample.group_id, sample.label)
        if previous != sample.label:
            raise ValueError(f"Vehicle group has mixed labels: {sample.group_id}")

    rng = random.Random(seed)
    test_groups: set[str] = set()
    for label in (0, 1):
        groups = sorted(group for group, value in group_labels.items() if value == label)
        if len(groups) < 2:
            raise ValueError("Each class needs at least two vehicle groups")
        rng.shuffle(groups)
        count = max(1, round(len(groups) * test_fraction))
        test_groups.update(groups[:count])

    development = [sample for sample in samples if sample.group_id not in test_groups]
    locked_test = [sample for sample in samples if sample.group_id in test_groups]
    return development, locked_test


class ClaimImageDataset:
    """Torch-compatible dataset without relying on ImageFolder suffix filtering."""

    def __init__(self, samples: Sequence[ImageSample], transform: Callable):
        self.samples = list(samples)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        import torch

        sample = self.samples[index]
        image = self.transform(load_rgb_image(sample.path))
        return image, torch.tensor(float(sample.label), dtype=torch.float32), index
