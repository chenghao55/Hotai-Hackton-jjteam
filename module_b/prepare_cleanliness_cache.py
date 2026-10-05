"""Create a local 512px MoLa-VI training cache without modifying source data."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil

from .cleanliness_dataset import (
    dataset_manifest_sha256,
    discover_mola_vi_samples,
    load_cleanliness_mask,
)
from .damage_segmentation import resize_and_pad_pair
from .dataset import load_rgb_image
from .model import CLEANLINESS_IMAGE_SIZE


def build_cache(
    source_root: Path, output_root: Path, *, image_size: int, workers: int = 8
) -> None:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if source_root == output_root or source_root in output_root.parents:
        raise ValueError("Cache root must not equal or contain the source dataset")
    samples = discover_mola_vi_samples(source_root, validate_images=False)
    output_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / "dataset.json", output_root / "dataset.json")

    if workers <= 0:
        raise ValueError("workers must be positive")

    def cache_one(sample) -> None:
        relative = Path(sample.vehicle_id) / sample.view / sample.image_path.name
        image_output = output_root / "IMAGES" / relative
        mask_output = output_root / "SEGMENTATIONS" / relative
        if not image_output.is_file() or not mask_output.is_file():
            image = load_rgb_image(sample.image_path)
            mask, _ = load_cleanliness_mask(sample.mask_path, image.size)
            # Keep the official raw IDs in the cache. The dataset loader maps
            # 4/5 to stain/dirt when reading a mask; writing mapped 1/2 IDs
            # here would make a second load interpret them as background.
            import numpy as np
            from PIL import Image

            mapped = np.asarray(mask, dtype=np.uint8)
            raw_mask = np.zeros(mapped.shape, dtype=np.uint8)
            raw_mask[mapped == 1] = 4
            raw_mask[mapped == 2] = 5
            mask = Image.fromarray(raw_mask, mode="L")
            image, mask = resize_and_pad_pair(image, mask, image_size)
            image_output.parent.mkdir(parents=True, exist_ok=True)
            mask_output.parent.mkdir(parents=True, exist_ok=True)
            image.save(image_output, format="JPEG", quality=95, optimize=True)
            mask.save(mask_output, format="PNG", optimize=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index, _ in enumerate(executor.map(cache_one, samples), start=1):
            if index % 100 == 0 or index == len(samples):
                print(
                    json.dumps(
                        {"event": "cache_progress", "completed": index, "total": len(samples)}
                    ),
                    flush=True,
                )

    cached = discover_mola_vi_samples(output_root, validate_images=True)
    expected = dataset_manifest_sha256(samples)
    actual = dataset_manifest_sha256(cached)
    source_ids = {sample.original_id for sample in samples}
    cached_ids = {sample.original_id for sample in cached}
    if cached_ids != source_ids:
        raise RuntimeError("Cached MoLa-VI sample IDs differ from the source manifest")
    marker = {
        "source_root": str(source_root),
        "image_size": image_size,
        "sample_count": len(cached),
        "source_manifest_sha256": expected,
        "cached_manifest_sha256": actual,
    }
    (output_root / "cache_manifest.json").write_text(
        json.dumps(marker, indent=2), encoding="utf-8"
    )
    print(json.dumps({"event": "cache_complete", **marker}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--image-size", type=int, default=CLEANLINESS_IMAGE_SIZE)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    build_cache(
        args.source_root,
        args.output_root,
        image_size=args.image_size,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
