"""Build an auditable condition-training manifest from local licensed datasets."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from .condition_dataset import CONDITION_SUPPORTED_SUFFIXES, _validate_source
from .condition_schema import CATEGORY_ORDER


HITL_SOURCE_URL = (
    "https://humansintheloop.org/resources/datasets/car-parts-and-car-damages-dataset/"
)
HITL_SOURCE = {
    "id": "hitl-car-parts-and-damages",
    "title": "Car Parts and Car Damages Dataset",
    "creator": "Humans in the Loop",
    "source_url": HITL_SOURCE_URL,
    "license": "CC0-1.0",
    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "license_evidence_url": HITL_SOURCE_URL,
}

HITL_CATEGORY_MAP = {
    "scratch": "scratch",
    "dent": "collision_damage",
    "cracked": "collision_damage",
    "broken part": "collision_damage",
    "missing part": "collision_damage",
}
HITL_DAMAGE_CLASSES = frozenset(
    {
        "scratch",
        "dent",
        "cracked",
        "broken part",
        "missing part",
        "flaking",
        "paint chip",
        "corrosion",
    }
)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON: {path}") from exc


def coco_samples(annotation_path: Path, images_root: Path) -> list[dict[str, object]]:
    """Convert COCO image/category annotations into image-level target labels."""
    raw = _read_json(annotation_path)
    if not isinstance(raw, dict):
        raise ValueError(f"COCO annotation must be an object: {annotation_path}")
    images = raw.get("images")
    categories = raw.get("categories")
    annotations = raw.get("annotations")
    if not all(isinstance(value, list) for value in (images, categories, annotations)):
        raise ValueError(f"COCO annotation is missing images/categories/annotations: {annotation_path}")
    category_names = {
        category["id"]: str(category["name"]).strip().lower()
        for category in categories
        if isinstance(category, dict) and "id" in category and "name" in category
    }
    labels_by_image: dict[object, set[str]] = {}
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        mapped = HITL_CATEGORY_MAP.get(category_names.get(annotation.get("category_id"), ""))
        if mapped is not None:
            labels_by_image.setdefault(annotation.get("image_id"), set()).add(mapped)

    result: list[dict[str, object]] = []
    for image in images:
        if not isinstance(image, dict) or "id" not in image or "file_name" not in image:
            raise ValueError(f"COCO image entries require id and file_name: {annotation_path}")
        image_path = (images_root / str(image["file_name"])).resolve()
        if image_path.suffix.lower() not in CONDITION_SUPPORTED_SUFFIXES:
            continue
        if not image_path.is_file():
            raise ValueError(f"COCO image does not exist: {image_path}")
        labels = labels_by_image.get(image["id"], set())
        result.append(
            {
                "image": str(image_path),
                "source_id": HITL_SOURCE["id"],
                "original_id": f"{annotation_path.stem}:{image['id']}",
                "labels": [category for category in CATEGORY_ORDER if category in labels],
            }
        )
    return result


def supervisely_samples(dataset_root: Path) -> list[dict[str, object]]:
    """Convert the official HITL Supervisely export to image-level targets.

    The Kaggle v2 archive uses ``File*/ann/<image-name>.json`` beside an
    ``img`` directory.  We derive targets from ``classTitle`` rather than the
    misleading top-level directory names in that archive.
    """
    root = dataset_root.resolve()
    all_annotation_paths = sorted(root.glob("**/ann/*.json"))
    if not all_annotation_paths:
        raise ValueError(f"No Supervisely annotation files found under: {root}")

    # The archive stores some pixels twice: once with vehicle-part polygons and
    # once with damage polygons. Missing damage labels in a part-only export are
    # unknown, not negatives, so select collections by their annotation taxonomy.
    annotations_by_directory: dict[Path, list[tuple[Path, dict[str, object]]]] = {}
    for annotation_path in all_annotation_paths:
        raw = _read_json(annotation_path)
        if not isinstance(raw, dict) or not isinstance(raw.get("objects"), list):
            raise ValueError(f"Invalid Supervisely annotation: {annotation_path}")
        annotations_by_directory.setdefault(annotation_path.parent, []).append(
            (annotation_path, raw)
        )

    selected: list[tuple[Path, dict[str, object]]] = []
    for annotations in annotations_by_directory.values():
        class_titles = {
            str(annotation.get("classTitle", "")).strip().lower()
            for _, raw in annotations
            for annotation in raw["objects"]
            if isinstance(annotation, dict)
        }
        if class_titles & HITL_DAMAGE_CLASSES:
            selected.extend(annotations)
    if not selected:
        raise ValueError(f"No HITL damage annotation collection found under: {root}")

    result: list[dict[str, object]] = []
    seen_images: set[Path] = set()
    for annotation_path, raw in sorted(selected, key=lambda item: item[0]):
        image_name = annotation_path.name.removesuffix(".json")
        image_path = (annotation_path.parent.parent / "img" / image_name).resolve()
        if image_path.suffix.lower() not in CONDITION_SUPPORTED_SUFFIXES:
            continue
        if not image_path.is_file():
            raise ValueError(f"Supervisely image does not exist: {image_path}")
        if image_path in seen_images:
            raise ValueError(f"Image has multiple Supervisely annotations: {image_path}")
        seen_images.add(image_path)

        labels: set[str] = set()
        for annotation in raw["objects"]:
            if not isinstance(annotation, dict):
                continue
            class_title = str(annotation.get("classTitle", "")).strip().lower()
            mapped = HITL_CATEGORY_MAP.get(class_title)
            if mapped is not None:
                labels.add(mapped)
        result.append(
            {
                "image": str(image_path),
                "source_id": HITL_SOURCE["id"],
                "original_id": annotation_path.relative_to(root).as_posix(),
                "labels": [category for category in CATEGORY_ORDER if category in labels],
            }
        )
    return result


def build_manifest(
    *,
    hitl_annotations: list[Path] | None,
    hitl_images_root: Path | None,
    hitl_root: Path | None,
    hitl_version: str,
    retrieved_at: str,
) -> dict[str, object]:
    if not hitl_version.strip():
        raise ValueError("HITL version must be nonempty")
    hitl_source = {
        **HITL_SOURCE,
        "version": hitl_version.strip(),
        "retrieved_at": retrieved_at,
    }
    _validate_source(hitl_source)
    if (hitl_root is None) == (hitl_annotations is None):
        raise ValueError("Provide exactly one of hitl_root or hitl_annotations")
    if hitl_annotations is not None and hitl_images_root is None:
        raise ValueError("hitl_images_root is required with hitl_annotations")
    samples: list[dict[str, object]] = []
    if hitl_root is not None:
        samples.extend(supervisely_samples(hitl_root))
    else:
        assert hitl_annotations is not None and hitl_images_root is not None
        for annotation_path in hitl_annotations:
            samples.extend(coco_samples(annotation_path, hitl_images_root))

    return {"schema_version": 1, "sources": [hitl_source], "samples": samples}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    hitl = parser.add_mutually_exclusive_group(required=True)
    hitl.add_argument("--hitl-root", type=Path)
    hitl.add_argument("--hitl-annotations", type=Path, nargs="+")
    parser.add_argument("--hitl-images-root", type=Path)
    parser.add_argument("--hitl-version", required=True)
    parser.add_argument("--retrieved-at", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest(
        hitl_annotations=args.hitl_annotations,
        hitl_images_root=args.hitl_images_root,
        hitl_root=args.hitl_root,
        hitl_version=args.hitl_version,
        retrieved_at=args.retrieved_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(args.output), "samples": len(manifest["samples"])}))


if __name__ == "__main__":
    main()
