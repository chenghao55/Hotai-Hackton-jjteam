"""Build a local, unverified borrow/return candidate inventory from folders.

This tool never edits source photos. Filename similarity is not
evidence of the same vehicle or rental; every row requires human review.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
import re


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".jfif", ".png"}
SLOTS = {"左前": "front_left", "右前": "front_right",
         "左後": "rear_left", "右後": "rear_right"}
NAME_PATTERN = re.compile(
    r"(?P<vehicle>[A-Z]{2,4}-?\d{3,5})\s*"
    r"(?P<slot>左前|右前|左後|右後)\s*"
    r"(?P<phase>借|還)(?P<version>\d*)$",
    re.IGNORECASE,
)


def parse_name(filename: str) -> dict[str, str] | None:
    """Parse only a known corner/phase suffix; leave other files for review."""
    stem = Path(filename).stem
    match = NAME_PATTERN.search(stem)
    if not match:
        return None
    return {
        "vehicle_key": match["vehicle"].replace("-", "").upper(),
        "capture_slot": SLOTS[match["slot"]],
        "phase": "borrow" if match["phase"] == "借" else "return",
        "version": match["version"] or "1",
    }


def _row_id(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def build_inventory(source_root: Path, group_names: tuple[str, ...]) -> dict:
    """Read only named source folders and return candidates plus exceptions."""
    if not source_root.is_dir():
        raise ValueError(f"Source directory not found: {source_root}")
    if not group_names or len(set(group_names)) != len(group_names):
        raise ValueError("Specify unique group folder names")
    groups: dict[tuple[str, str, str], dict[str, list[dict]]] = defaultdict(
        lambda: {"borrow": [], "return": []})
    exceptions: list[dict] = []
    folder_count = 0
    image_count = 0
    for group_name in sorted(group_names):
        folder = source_root / group_name
        if not folder.is_dir():
            raise ValueError(f"Group directory not found: {folder}")
        folder_count += 1
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            image_count += 1
            item = {
                "source_folder": str(folder),
                "file_path": str(path),
                "file_bytes": path.stat().st_size,
            }
            parsed = parse_name(path.name)
            if parsed is None:
                exceptions.append({**item, "reason": "filename_not_recognized"})
                continue
            item.update(parsed)
            groups[(folder.name, parsed["vehicle_key"],
                    parsed["capture_slot"])][parsed["phase"]].append(item)

    rows: list[dict] = []
    for (group, vehicle, slot), sides in sorted(groups.items()):
        borrows = sorted(sides["borrow"], key=lambda x: x["file_path"])
        returns = sorted(sides["return"],
                         key=lambda x: (int(x["version"]), x["file_path"]))
        candidates = returns or [None]
        for returned in candidates:
            borrow = borrows[0] if len(borrows) == 1 else None
            status = ("candidate" if borrow and returned else
                      "multiple_borrow" if len(borrows) > 1 else
                      "missing_borrow" if returned else "missing_return")
            rows.append({
                "candidate_id": _row_id(group, vehicle, slot,
                                        returned["file_path"] if returned else ""),
                "source_group": group,
                "vehicle_key_from_filename": vehicle,
                "capture_slot": slot,
                "borrow_path": borrow["file_path"] if borrow else "",
                "return_path": returned["file_path"] if returned else "",
                "return_version_from_filename": returned["version"] if returned else "",
                "source_folder": (returned or borrow or borrows[0])["source_folder"],
                "borrow_candidate_count": len(borrows),
                "return_candidate_count": len(returns),
                "filename_status": status,
                "same_vehicle_review": "",
                "same_rental_review": "",
                "same_view_review": "",
                "comparability_review": "",
                "visible_change_review": "",
                "review_notes": "",
            })
    return {
        "source_root": str(source_root),
        "folder_count": folder_count,
        "image_count": image_count,
        "rows": rows,
        "exceptions": exceptions,
    }


def write_review_csv(inventory: dict, output: Path, exceptions_output: Path) -> None:
    """Save private local review lists without image data or verified claims."""
    output.parent.mkdir(parents=True, exist_ok=True)
    exceptions_output.parent.mkdir(parents=True, exist_ok=True)
    columns = {
        "candidate_id": "候選編號",
        "source_group": "來源資料夾",
        "vehicle_key_from_filename": "檔名車輛鍵",
        "capture_slot": "車角代碼",
        "borrow_path": "借車原圖路徑",
        "return_path": "還車原圖路徑",
        "return_version_from_filename": "還車版本",
        "filename_status": "檔名配對狀態",
        "same_vehicle_review": "人工確認同車",
        "same_rental_review": "人工確認同次租借",
        "same_view_review": "人工確認同視角",
        "comparability_review": "人眼可比較性",
        "visible_change_review": "可見真變化",
        "review_notes": "人工備註",
    }
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(columns.values()))
        writer.writeheader()
        for row in inventory["rows"]:
            writer.writerow({label: row[key] or ("待確認" if key.endswith("_review") else "")
                             for key, label in columns.items()})
    with exceptions_output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["原圖路徑", "檔案大小(bytes)", "原因"])
        writer.writeheader()
        for item in inventory["exceptions"]:
            writer.writerow({"原圖路徑": item["file_path"],
                             "檔案大小(bytes)": item["file_bytes"],
                             "原因": item["reason"]})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--group", required=True, action="append",
                        help="Immediate folder name under source root; repeat for each group")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--exceptions-csv-output", type=Path)
    args = parser.parse_args()
    if bool(args.csv_output) != bool(args.exceptions_csv_output):
        parser.error("--csv-output and --exceptions-csv-output must be supplied together")
    inventory = build_inventory(args.source_root, tuple(args.group))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    if args.csv_output:
        write_review_csv(inventory, args.csv_output, args.exceptions_csv_output)
    print(json.dumps({"folders": inventory["folder_count"],
                      "images": inventory["image_count"],
                      "candidate_rows": len(inventory["rows"]),
                      "exceptions": len(inventory["exceptions"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
