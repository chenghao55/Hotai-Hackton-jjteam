"""Licensed manifest loading and leak-resistant samples for condition training."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import random
from typing import Callable, Sequence

from PIL import Image

from .condition_schema import CATEGORY_ORDER
from .dataset import ImageDecodeError, load_rgb_image


ALLOWED_LICENSES = frozenset({"CC0-1.0", "CC-BY-4.0"})
CONDITION_SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg", ".jfif", ".png"})
REQUIRED_SOURCE_FIELDS = (
    "id",
    "title",
    "creator",
    "source_url",
    "license",
    "license_url",
    "license_evidence_url",
    "version",
    "retrieved_at",
)


@dataclass(frozen=True)
class ConditionSample:
    path: Path
    labels: tuple[float, ...]
    group_id: str
    source_id: str
    original_id: str
    perceptual_hash: str

    def __post_init__(self) -> None:
        if len(self.labels) != len(CATEGORY_ORDER) or any(value not in {0.0, 1.0} for value in self.labels):
            raise ValueError("labels must be a binary value for every supported category")
        if not all((self.group_id, self.source_id, self.original_id, self.perceptual_hash)):
            raise ValueError("sample identifiers must be nonempty")


@dataclass(frozen=True)
class ConditionManifest:
    path: Path
    sources: tuple[dict[str, str], ...]
    samples: tuple[ConditionSample, ...]
    sha256: str


def perceptual_hash(image_path: str | Path) -> str:
    """Return a compact difference hash used only for split/dedup grouping."""
    image = load_rgb_image(image_path).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(image.get_flattened_data())
    bits = []
    for row in range(8):
        offset = row * 9
        bits.extend(pixels[offset + column] > pixels[offset + column + 1] for column in range(8))
    value = sum(int(bit) << index for index, bit in enumerate(bits))
    return f"{value:016x}"


def validate_condition_image(path: str | Path) -> None:
    """Validate a JPEG/JFIF or PNG image without modifying it."""
    try:
        with Image.open(path, formats=("JPEG", "PNG")) as image:
            image.verify()
    except (OSError, SyntaxError) as exc:
        raise ImageDecodeError(f"Invalid JPEG/JFIF/PNG image: {path}") from exc


def _validate_source(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("Each manifest source must be an object")
    source: dict[str, str] = {}
    for field in REQUIRED_SOURCE_FIELDS:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Source {field} must be a nonempty string")
        source[field] = value.strip()
    if source["license"] not in ALLOWED_LICENSES:
        raise ValueError(
            f"Unsupported source license {source['license']!r}; only CC0-1.0 and CC-BY-4.0 are allowed"
        )
    if not source["source_url"].startswith("https://"):
        raise ValueError("Source source_url must use HTTPS")
    if not source["license_url"].startswith("https://"):
        raise ValueError("Source license_url must use HTTPS")
    if not source["license_evidence_url"].startswith("https://"):
        raise ValueError("Source license_evidence_url must use HTTPS")
    return source


def _manifest_digest(raw: object) -> str:
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def load_condition_manifest(
    manifest_path: str | Path, *, validate_images: bool = True
) -> ConditionManifest:
    path = Path(manifest_path).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read condition dataset manifest: {path}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Condition manifest schema_version must be 1")
    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Condition manifest must contain at least one source")
    sources = tuple(_validate_source(item) for item in raw_sources)
    source_ids = [source["id"] for source in sources]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Condition manifest source ids must be unique")

    raw_samples = raw.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("Condition manifest must contain at least one sample")
    samples: list[ConditionSample] = []
    by_hash: dict[str, ConditionSample] = {}
    for item in raw_samples:
        if not isinstance(item, dict):
            raise ValueError("Each condition sample must be an object")
        source_id = item.get("source_id")
        original_id = item.get("original_id")
        image_value = item.get("image")
        raw_labels = item.get("labels")
        if source_id not in source_ids:
            raise ValueError(f"Unknown sample source_id: {source_id!r}")
        if not isinstance(original_id, str) or not original_id.strip():
            raise ValueError("Sample original_id must be a nonempty string")
        if not isinstance(image_value, str) or not image_value.strip():
            raise ValueError("Sample image must be a nonempty path string")
        if not isinstance(raw_labels, list) or any(label not in CATEGORY_ORDER for label in raw_labels):
            raise ValueError("Sample labels must be a list of supported categories")
        if len(set(raw_labels)) != len(raw_labels):
            raise ValueError("Sample labels must not contain duplicates")
        image_path = Path(image_value)
        if not image_path.is_absolute():
            image_path = path.parent / image_path
        image_path = image_path.resolve()
        if image_path.suffix.lower() not in CONDITION_SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported sample image suffix: {image_path}")
        if validate_images:
            validate_condition_image(image_path)
        digest = perceptual_hash(image_path)
        label_vector = tuple(float(category in raw_labels) for category in CATEGORY_ORDER)
        sample = ConditionSample(
            path=image_path,
            labels=label_vector,
            group_id=f"phash:{digest}",
            source_id=source_id,
            original_id=original_id.strip(),
            perceptual_hash=digest,
        )
        previous = by_hash.get(digest)
        if previous is not None:
            if previous.labels != sample.labels:
                raise ValueError(f"Duplicate image has conflicting labels: {image_path}")
            continue
        by_hash[digest] = sample
        samples.append(sample)
    return ConditionManifest(path, sources, tuple(samples), _manifest_digest(raw))


def split_condition_samples(
    samples: Sequence[ConditionSample],
    *,
    seed: int,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
    attempts: int = 10_000,
) -> tuple[list[ConditionSample], list[ConditionSample], list[ConditionSample]]:
    """Find a deterministic group split where every class has positives in each set."""
    if not 0.0 < validation_fraction < 1.0 or not 0.0 < test_fraction < 1.0:
        raise ValueError("validation_fraction and test_fraction must be within (0, 1)")
    if validation_fraction + test_fraction >= 1.0:
        raise ValueError("validation_fraction and test_fraction must sum to less than 1")
    groups: dict[str, list[ConditionSample]] = {}
    for sample in samples:
        groups.setdefault(sample.group_id, []).append(sample)
    group_ids = sorted(groups)
    if len(group_ids) < 3:
        raise ValueError("Condition dataset needs at least three independent image groups")
    rng = random.Random(seed)
    test_count = max(1, round(len(group_ids) * test_fraction))
    validation_count = max(1, round(len(group_ids) * validation_fraction))

    def complete(partition: Sequence[ConditionSample]) -> bool:
        return bool(partition) and all(
            any(sample.labels[index] == 1.0 for sample in partition)
            and any(sample.labels[index] == 0.0 for sample in partition)
            for index in range(len(CATEGORY_ORDER))
        )

    for _ in range(attempts):
        shuffled = group_ids.copy()
        rng.shuffle(shuffled)
        test_groups = set(shuffled[:test_count])
        validation_groups = set(shuffled[test_count : test_count + validation_count])
        train_groups = set(shuffled[test_count + validation_count :])
        train = [sample for group in train_groups for sample in groups[group]]
        validation = [sample for group in validation_groups for sample in groups[group]]
        test = [sample for group in test_groups for sample in groups[group]]
        if complete(train) and complete(validation) and complete(test):
            return train, validation, test
    raise ValueError(
        "Unable to create train/validation/test splits with positives for every category"
    )


class ConditionImageDataset:
    def __init__(self, samples: Sequence[ConditionSample], transform: Callable):
        self.samples = list(samples)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        import torch

        sample = self.samples[index]
        image = self.transform(load_rgb_image(sample.path))
        labels = torch.tensor(sample.labels, dtype=torch.float32)
        return image, labels, index
