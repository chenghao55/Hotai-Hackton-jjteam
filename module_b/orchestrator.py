"""Module B orchestration from uploaded photo bytes to a Module D Case."""

from dataclasses import dataclass

from module_a import CaptureSlot, PhotoNotFoundError, PhotoType, get_photo_info
from module_d import Case, DetectionInput, create_case
from module_d.policy import DecisionPolicy

from .analyzer import AIFinding, AIAnalyzer
from .interface import ModuleB


@dataclass(frozen=True)
class _EvidencePair:
    borrow_photo_id: str | None
    return_photo_id: str


@dataclass(frozen=True)
class _PreparedPhotos:
    damage_photos: list[tuple[str, bytes]]
    cleanliness_photos: list[tuple[str, bytes]]
    evidence_by_photo_id: dict[str, _EvidencePair]


_DAMAGE_FIXED_SLOTS = frozenset({
    CaptureSlot.FRONT_LEFT,
    CaptureSlot.FRONT_RIGHT,
    CaptureSlot.REAR_LEFT,
    CaptureSlot.REAR_RIGHT,
    CaptureSlot.REAR,
})

_AUXILIARY_SLOTS = frozenset({
    CaptureSlot.FUEL_PARKING_CARD,
})

_INTERIOR_SLOTS = frozenset({CaptureSlot.INTERIOR_FRONT, CaptureSlot.INTERIOR_REAR})


class CaseBuildingModuleB(ModuleB):
    """Delegates AI findings and all Case-domain decisions to their owners."""

    def __init__(
        self,
        analyzer: AIAnalyzer,
        *,
        policy: DecisionPolicy,
        cleanliness_analyzer: AIAnalyzer | None = None,
    ) -> None:
        """Store the AI analyzer and decision policy used for every case."""
        self._analyzer = analyzer
        self._cleanliness_analyzer = cleanliness_analyzer
        self._policy = policy

    def analyze(self, case_id: str, photos: list[tuple[str, bytes]]) -> Case:
        """Analyze model-relevant photos, attach evidence, and create a Case."""
        prepared = self._prepare_photos(photos)
        findings = self._validated_findings(
            self._analyzer.analyze(prepared.damage_photos), prepared.damage_photos
        )
        if self._cleanliness_analyzer is not None:
            findings.extend(
                self._validated_findings(
                    self._cleanliness_analyzer.analyze(prepared.cleanliness_photos),
                    prepared.cleanliness_photos,
                )
            )
        detection_inputs = [
            self._to_detection_input(finding, prepared.evidence_by_photo_id)
            for finding in findings
        ]
        return create_case(case_id, detection_inputs, policy=self._policy)

    @staticmethod
    def _validated_findings(
        findings: list[AIFinding], photos: list[tuple[str, bytes]]
    ) -> list[AIFinding]:
        if not isinstance(findings, list):
            raise ValueError("AI analyzer must return a list of AIFinding objects")
        allowed_photo_ids = {photo_id for photo_id, _ in photos}
        for finding in findings:
            if not isinstance(finding, AIFinding):
                raise ValueError("AI analyzer must return only AIFinding objects")
            if finding.source_photo_id not in allowed_photo_ids:
                raise ValueError(
                    "AI finding source_photo_id must match one of the analyzed photos"
                )
        return list(findings)

    @staticmethod
    def _prepare_photos(
        photos: list[tuple[str, bytes]],
    ) -> _PreparedPhotos:
        """Validate metadata and prepare model inputs with their evidence.

        Damage slots accept either a complete borrow/return pair or return-only
        evidence. The card slot is always auxiliary. Return-side interior slots
        are prepared separately for the optional cleanliness model.
        """
        if not isinstance(photos, list):
            raise TypeError("photos must be a list of (photo_id, bytes) pairs")
        if not photos:
            raise ValueError("photos must not be empty")

        fixed_slots: dict[CaptureSlot, dict[PhotoType, str]] = {}
        other_damage_returns: list[str] = []
        seen_photo_ids: set[str] = set()
        analyzer_photos: list[tuple[str, bytes]] = []
        cleanliness_photos: list[tuple[str, bytes]] = []
        interior_returns: list[str] = []

        for photo in photos:
            if not isinstance(photo, tuple) or len(photo) != 2:
                raise ValueError("photos must contain only (photo_id, bytes) pairs")
            photo_id, image_bytes = photo
            if not isinstance(photo_id, str) or not photo_id.strip():
                raise ValueError("photo_id must be a nonempty string")
            if photo_id in seen_photo_ids:
                raise ValueError(f"duplicate photo_id: {photo_id!r}")
            if not isinstance(image_bytes, bytes):
                raise TypeError("photo bytes must be bytes")
            seen_photo_ids.add(photo_id)

            try:
                info = get_photo_info(photo_id)
            except PhotoNotFoundError as exc:
                raise ValueError(
                    f"unknown or invalid photo metadata for photo_id: {photo_id!r}"
                ) from exc

            if (
                info.photo_id != photo_id
                or not isinstance(info.photo_type, PhotoType)
                or not isinstance(info.capture_slot, CaptureSlot)
            ):
                raise ValueError(f"invalid photo metadata for photo_id: {photo_id!r}")

            if info.capture_slot == CaptureSlot.OTHER_DAMAGE:
                if info.photo_type != PhotoType.RETURN:
                    raise ValueError("OTHER_DAMAGE photos must be return photos")
                other_damage_returns.append(photo_id)
                analyzer_photos.append(photo)
                continue

            if info.capture_slot in _AUXILIARY_SLOTS:
                continue

            if info.capture_slot in _INTERIOR_SLOTS:
                if info.photo_type == PhotoType.RETURN:
                    interior_returns.append(photo_id)
                    cleanliness_photos.append(photo)
                continue

            if info.capture_slot not in _DAMAGE_FIXED_SLOTS:
                raise ValueError(f"unsupported capture slot: {info.capture_slot.value!r}")

            slot_photos = fixed_slots.setdefault(info.capture_slot, {})
            if info.photo_type in slot_photos:
                raise ValueError(
                    f"duplicate {info.photo_type.value} photo for capture slot "
                    f"{info.capture_slot.value!r}"
                )
            slot_photos[info.photo_type] = photo_id
            analyzer_photos.append(photo)

        evidence_by_photo_id: dict[str, _EvidencePair] = {}
        for capture_slot, slot_photos in fixed_slots.items():
            borrow_photo_id = slot_photos.get(PhotoType.BORROW)
            return_photo_id = slot_photos.get(PhotoType.RETURN)
            if return_photo_id is None:
                raise ValueError(
                    f"missing matching return photo for capture slot {capture_slot.value!r}"
                )
            pair = _EvidencePair(borrow_photo_id, return_photo_id)
            if borrow_photo_id is not None:
                evidence_by_photo_id[borrow_photo_id] = pair
            evidence_by_photo_id[return_photo_id] = pair

        for return_photo_id in other_damage_returns:
            evidence_by_photo_id[return_photo_id] = _EvidencePair(None, return_photo_id)

        for return_photo_id in interior_returns:
            evidence_by_photo_id[return_photo_id] = _EvidencePair(None, return_photo_id)

        return _PreparedPhotos(analyzer_photos, cleanliness_photos, evidence_by_photo_id)

    @staticmethod
    def _to_detection_input(
        finding: AIFinding,
        evidence_by_photo_id: dict[str, _EvidencePair],
    ) -> DetectionInput:
        """Attach a finding to its photo evidence for Module D case creation."""
        if not isinstance(finding, AIFinding):
            raise ValueError("AI analyzer must return only AIFinding objects")
        evidence = evidence_by_photo_id.get(finding.source_photo_id)
        if evidence is None:
            raise ValueError(
                "AI finding source_photo_id must match one of the analyzed photos"
            )
        return DetectionInput(
            detection_id=finding.detection_id,
            borrow_photo_id=evidence.borrow_photo_id,
            return_photo_id=evidence.return_photo_id,
            source_photo_id=finding.source_photo_id,
            category=finding.category,
            severity=finding.severity,
            confidence=finding.confidence,
        )
