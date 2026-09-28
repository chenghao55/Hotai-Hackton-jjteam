from pathlib import Path
from types import SimpleNamespace

import pytest

from module_a import CaptureSlot, Photo, PhotoNotFoundError, PhotoType
from module_b import AIFinding, AIAnalyzer, CaseBuildingModuleB
from module_b import orchestrator
from module_d import ConditionCategory, DetectionInput, ReviewState, Severity, demo_policy


class RecordingAnalyzer(AIAnalyzer):
    def __init__(self, findings: list[AIFinding] | None = None) -> None:
        self.findings = findings or []
        self.received: list[tuple[str, bytes]] | None = None

    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        self.received = list(photos)
        return list(self.findings)


@pytest.fixture
def photo_metadata(monkeypatch):
    metadata: dict[str, object] = {}

    def lookup(photo_id: str):
        try:
            return metadata[photo_id]
        except KeyError as exc:
            raise PhotoNotFoundError(f"Photo not found: {photo_id!r}") from exc

    monkeypatch.setattr(orchestrator, "get_photo_info", lookup)
    return metadata


def add_photo(
    metadata: dict[str, object],
    photo_id: str,
    photo_type: PhotoType,
    capture_slot: CaptureSlot,
) -> tuple[str, bytes]:
    metadata[photo_id] = Photo(
        photo_id=photo_id,
        photo_type=photo_type,
        capture_slot=capture_slot,
        mime_type="image/jpeg",
        file_path=Path(f"{photo_id}.bin"),
    )
    return photo_id, f"bytes:{photo_id}".encode()


def finding(photo_id: str, detection_id: str = "finding-1") -> AIFinding:
    return AIFinding(
        detection_id=detection_id,
        source_photo_id=photo_id,
        category=ConditionCategory.SCRATCH,
        severity=Severity.MINOR,
        confidence=0.65,
    )


def build(analyzer: AIAnalyzer) -> CaseBuildingModuleB:
    return CaseBuildingModuleB(analyzer, policy=demo_policy())


def test_single_fixed_pair_remains_compatible_and_uses_d_rules(photo_metadata):
    photos = [
        add_photo(photo_metadata, "borrow-front", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-front", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
    ]
    analyzer = RecordingAnalyzer([finding("return-front")])

    case = build(analyzer).analyze("case-1", photos)

    assert analyzer.received == photos
    detection = case.detections[0]
    assert detection.borrow_photo_id == "borrow-front"
    assert detection.return_photo_id == "return-front"
    assert detection.source_photo_id == "return-front"
    assert detection.review_state == ReviewState.NEEDS_REVIEW
    assert case.priority_score == 20


def test_multiple_fixed_pairs_map_each_finding_to_its_slot(photo_metadata):
    photos = [
        add_photo(photo_metadata, "borrow-front", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-front", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "borrow-rear", PhotoType.BORROW, CaptureSlot.REAR),
        add_photo(photo_metadata, "return-rear", PhotoType.RETURN, CaptureSlot.REAR),
    ]
    analyzer = RecordingAnalyzer(
        [finding("borrow-front", "front-finding"), finding("return-rear", "rear-finding")]
    )

    case = build(analyzer).analyze("case-1", photos)

    by_id = {detection.detection_id: detection for detection in case.detections}
    assert (by_id["front-finding"].borrow_photo_id, by_id["front-finding"].return_photo_id) == (
        "borrow-front",
        "return-front",
    )
    assert (by_id["rear-finding"].borrow_photo_id, by_id["rear-finding"].return_photo_id) == (
        "borrow-rear",
        "return-rear",
    )


def test_shuffled_photo_order_is_valid(photo_metadata):
    photos = [
        add_photo(photo_metadata, "return-rear", PhotoType.RETURN, CaptureSlot.REAR),
        add_photo(photo_metadata, "borrow-front", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-front", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "borrow-rear", PhotoType.BORROW, CaptureSlot.REAR),
    ]
    analyzer = RecordingAnalyzer()

    case = build(analyzer).analyze("case-1", photos)

    assert analyzer.received == photos
    assert case.detections == []


def test_missing_matching_return_is_invalid(photo_metadata):
    photos = [
        add_photo(photo_metadata, "borrow-front", PhotoType.BORROW, CaptureSlot.FRONT_LEFT)
    ]

    with pytest.raises(ValueError, match="missing matching return.*front_left"):
        build(RecordingAnalyzer()).analyze("case-1", photos)


@pytest.mark.parametrize(
    "capture_slot",
    [
        CaptureSlot.FRONT_LEFT,
        CaptureSlot.FRONT_RIGHT,
        CaptureSlot.REAR_LEFT,
        CaptureSlot.REAR_RIGHT,
        CaptureSlot.REAR,
    ],
)
def test_return_only_damage_slot_is_valid(photo_metadata, capture_slot):
    photos = [
        add_photo(photo_metadata, "return-photo", PhotoType.RETURN, capture_slot)
    ]
    analyzer = RecordingAnalyzer([finding("return-photo")])

    case = build(analyzer).analyze("case-1", photos)

    assert analyzer.received == photos
    detection = case.detections[0]
    assert detection.borrow_photo_id is None
    assert detection.return_photo_id == "return-photo"
    assert detection.source_photo_id == "return-photo"


def test_duplicate_borrow_for_fixed_slot_is_invalid(photo_metadata):
    photos = [
        add_photo(photo_metadata, "borrow-front-1", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "borrow-front-2", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-front", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
    ]

    with pytest.raises(ValueError, match="duplicate borrow.*front_left"):
        build(RecordingAnalyzer()).analyze("case-1", photos)


def test_duplicate_return_for_fixed_slot_is_invalid(photo_metadata):
    photos = [
        add_photo(photo_metadata, "return-front-1", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-front-2", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
    ]

    with pytest.raises(ValueError, match="duplicate return.*front_left"):
        build(RecordingAnalyzer()).analyze("case-1", photos)


def test_multiple_return_other_damage_photos_create_return_only_evidence(photo_metadata):
    photos = [
        add_photo(photo_metadata, "extra-1", PhotoType.RETURN, CaptureSlot.OTHER_DAMAGE),
        add_photo(photo_metadata, "extra-2", PhotoType.RETURN, CaptureSlot.OTHER_DAMAGE),
    ]
    analyzer = RecordingAnalyzer(
        [finding("extra-1", "extra-finding-1"), finding("extra-2", "extra-finding-2")]
    )

    case = build(analyzer).analyze("case-1", photos)

    assert analyzer.received == photos
    assert [(d.borrow_photo_id, d.return_photo_id, d.source_photo_id) for d in case.detections] == [
        (None, "extra-1", "extra-1"),
        (None, "extra-2", "extra-2"),
    ]


def test_borrow_other_damage_metadata_is_invalid(photo_metadata):
    photo_metadata["invalid-extra"] = SimpleNamespace(
        photo_id="invalid-extra",
        photo_type=PhotoType.BORROW,
        capture_slot=CaptureSlot.OTHER_DAMAGE,
    )

    with pytest.raises(ValueError, match="OTHER_DAMAGE photos must be return photos"):
        build(RecordingAnalyzer()).analyze("case-1", [("invalid-extra", b"image")])


def test_only_damage_model_slots_are_sent_once_to_analyzer_in_input_order(photo_metadata):
    photos = [
        add_photo(photo_metadata, "return-extra-1", PhotoType.RETURN, CaptureSlot.OTHER_DAMAGE),
        add_photo(photo_metadata, "borrow-fuel", PhotoType.BORROW, CaptureSlot.FUEL_PARKING_CARD),
        add_photo(photo_metadata, "return-front", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-fuel", PhotoType.RETURN, CaptureSlot.FUEL_PARKING_CARD),
        add_photo(photo_metadata, "borrow-front", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-extra-2", PhotoType.RETURN, CaptureSlot.OTHER_DAMAGE),
    ]
    analyzer = RecordingAnalyzer()

    build(analyzer).analyze("case-1", photos)

    assert analyzer.received == [photos[0], photos[2], photos[4], photos[5]]
    assert len({photo_id for photo_id, _ in analyzer.received}) == len(analyzer.received)


@pytest.mark.parametrize(
    "capture_slot",
    [
        CaptureSlot.FUEL_PARKING_CARD,
        CaptureSlot.INTERIOR_FRONT,
        CaptureSlot.INTERIOR_REAR,
    ],
)
def test_auxiliary_slots_are_valid_but_filtered_from_analyzer(photo_metadata, capture_slot):
    photos = [
        add_photo(photo_metadata, "auxiliary-photo", PhotoType.RETURN, capture_slot)
    ]
    analyzer = RecordingAnalyzer()

    case = build(analyzer).analyze("case-1", photos)

    assert analyzer.received == []
    assert case.detections == []


def test_finding_cannot_claim_filtered_auxiliary_photo(photo_metadata):
    photos = [
        add_photo(
            photo_metadata,
            "interior-photo",
            PhotoType.RETURN,
            CaptureSlot.INTERIOR_FRONT,
        )
    ]

    with pytest.raises(ValueError, match="source_photo_id must match"):
        build(RecordingAnalyzer([finding("interior-photo")])).analyze("case-1", photos)


def test_duplicate_photo_id_is_invalid(photo_metadata):
    photo = add_photo(photo_metadata, "same-photo", PhotoType.RETURN, CaptureSlot.OTHER_DAMAGE)

    with pytest.raises(ValueError, match="duplicate photo_id"):
        build(RecordingAnalyzer()).analyze("case-1", [photo, photo])


def test_unknown_photo_metadata_is_reported_as_invalid(photo_metadata):
    with pytest.raises(ValueError, match="unknown or invalid photo metadata"):
        build(RecordingAnalyzer()).analyze("case-1", [("missing", b"image")])


def test_finding_source_must_be_one_of_the_analyzed_photos(photo_metadata):
    photos = [
        add_photo(photo_metadata, "borrow-front", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-front", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
    ]

    with pytest.raises(ValueError, match="source_photo_id must match"):
        build(RecordingAnalyzer([finding("not-an-input")])).analyze("case-1", photos)


def test_orchestrator_calls_module_d_create_case(photo_metadata, monkeypatch):
    photos = [
        add_photo(photo_metadata, "borrow-front", PhotoType.BORROW, CaptureSlot.FRONT_LEFT),
        add_photo(photo_metadata, "return-front", PhotoType.RETURN, CaptureSlot.FRONT_LEFT),
    ]
    analyzer = RecordingAnalyzer([finding("return-front")])
    real_create_case = orchestrator.create_case
    calls: list[tuple[str, list[DetectionInput]]] = []

    def recording_create_case(case_id, detections, *, policy):
        calls.append((case_id, detections))
        return real_create_case(case_id, detections, policy=policy)

    monkeypatch.setattr(orchestrator, "create_case", recording_create_case)

    case = build(analyzer).analyze("case-from-b", photos)

    assert case.case_id == "case-from-b"
    assert len(calls) == 1
    assert calls[0][0] == "case-from-b"
    assert all(isinstance(item, DetectionInput) for item in calls[0][1])
