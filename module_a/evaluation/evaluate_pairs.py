"""Run the local comparison core on filename-paired photo candidates.

This is an engineering smoke report, not a measured accuracy evaluation.
Source photos are read in place; accepted-photo storage is temporary and
deleted after the run. Output rows use candidate IDs rather than file paths.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from module_a import CaptureSlot, PhotoType, YoloDetector, load_config, save_photo
from module_a import photo as photo_storage
from module_a.photo_comparison import compare_stored_photos


def evaluate_manifest(manifest: dict, detector, *, limit: int | None = None) -> list[dict]:
    """Compare candidate rows without persisting source images in Module A."""
    rows = [row for row in manifest["rows"]
            if row["filename_status"] == "candidate"]
    if limit is not None:
        rows = rows[:limit]
    results = []
    original_photos_dir = photo_storage.PHOTOS_DIR
    try:
        with TemporaryDirectory() as storage_dir:
            photo_storage.PHOTOS_DIR = Path(storage_dir)
            for row in rows:
                started = perf_counter()
                item = {"candidate_id": row["candidate_id"],
                        "source_group": row["source_group"],
                        "capture_slot": row["capture_slot"]}
                try:
                    borrow_bytes = Path(row["borrow_path"]).read_bytes()
                    return_bytes = Path(row["return_path"]).read_bytes()
                    slot = CaptureSlot(row["capture_slot"])
                    borrow_id = save_photo(borrow_bytes, PhotoType.BORROW,
                                           slot, "image/jpeg")
                    return_id = save_photo(return_bytes, PhotoType.RETURN,
                                           slot, "image/jpeg")
                    result = compare_stored_photos(borrow_id, return_id,
                                                   detector=detector)
                    item.update({
                        "status": result.status,
                        "reason": result.reason,
                        "matching_points": result.matching_points,
                        "inlier_ratio": result.inlier_ratio,
                        "median_reprojection_error": result.median_reprojection_error,
                        "overlap_ratio": result.overlap_ratio,
                        "analysis_coverage_ratio": result.analysis_coverage_ratio,
                        "hotspot_count": len(result.hotspots),
                        "algorithm_version": result.algorithm_version,
                    })
                except (OSError, ValueError) as exc:
                    item.update({"status": "processing_error",
                                 "reason": type(exc).__name__})
                item["elapsed_seconds"] = round(perf_counter() - started, 3)
                results.append(item)
    finally:
        photo_storage.PHOTOS_DIR = original_photos_dir
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    detector = YoloDetector(args.checkpoint, load_config())
    results = evaluate_manifest(manifest, detector, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for result in results:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(json.dumps({"evaluated": len(results),
                      "statuses": dict(Counter(row["status"] for row in results)),
                      "reasons": dict(Counter(row["reason"] for row in results
                                              if row["reason"]))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
