"""Filename grouping must never silently turn uncertain photos into verified pairs."""

import csv

from module_a.evaluation.pair_manifest import (build_inventory, parse_name,
                                               write_review_csv)


def test_parse_corner_phase_and_return_revision():
    assert parse_name("RCG2235左前 借.jfif") == {
        "vehicle_key": "RCG2235", "capture_slot": "front_left",
        "phase": "borrow", "version": "1",
    }
    assert parse_name("RCR-7661 左後 還2.jpg") == {
        "vehicle_key": "RCR7661", "capture_slot": "rear_left",
        "phase": "return", "version": "2",
    }
    assert parse_name("RCG2235車況回報.jfif") is None


def test_folder_inventory_keeps_retake_and_unmatched_files_for_review(tmp_path):
    no_claim = tmp_path / "未索賠"
    claim = tmp_path / "索賠"
    no_claim.mkdir()
    claim.mkdir()
    for name in ("RCG2235左前 借.jfif", "RCG2235左前 還.jfif",
                 "RCG2235左前 還2.jfif", "RCG2235右前 借.jfif",
                 "RCG2235車況回報.jfif"):
        (no_claim / name).write_bytes(b"test")
    (claim / "RCG2235左前 還.jfif").write_bytes(b"test")

    inventory = build_inventory(tmp_path, ("未索賠", "索賠"))

    assert inventory["image_count"] == 6
    assert len(inventory["rows"]) == 4
    assert len(inventory["exceptions"]) == 1
    same_group = [row for row in inventory["rows"]
                  if row["source_group"] == "未索賠"
                  and row["capture_slot"] == "front_left"]
    assert [row["return_version_from_filename"] for row in same_group] == ["1", "2"]
    assert all(row["filename_status"] == "candidate" for row in same_group)
    assert all(row["same_rental_review"] == "" for row in same_group)
    assert any(row["filename_status"] == "missing_return"
               for row in inventory["rows"])
    assert any(row["source_group"] == "索賠" and
               row["filename_status"] == "missing_borrow"
               for row in inventory["rows"])

    review_path = tmp_path / "review.csv"
    other_path = tmp_path / "other.csv"
    write_review_csv(inventory, review_path, other_path)
    with review_path.open(encoding="utf-8-sig", newline="") as stream:
        exported = list(csv.DictReader(stream))
    with other_path.open(encoding="utf-8-sig", newline="") as stream:
        other = list(csv.DictReader(stream))
    assert len(exported) == 4
    assert exported[0]["人工確認同次租借"] == "待確認"
    assert len(other) == 1
