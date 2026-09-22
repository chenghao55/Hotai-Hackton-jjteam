"""Module B orchestration from uploaded photo bytes to a Module D Case."""

from module_a import PhotoType, get_photo_info
from module_d import Case, DetectionInput, create_case
from module_d.policy import DecisionPolicy

from .analyzer import AIFinding, AIAnalyzer
from .interface import ModuleB


class CaseBuildingModuleB(ModuleB):
    """Delegates AI findings and all Case-domain decisions to their owners."""

    def __init__(self, analyzer: AIAnalyzer, *, policy: DecisionPolicy) -> None:
        self._analyzer = analyzer
        self._policy = policy

    def analyze(self, case_id: str, photos: list[tuple[str, bytes]]) -> Case:
        borrow_photo_id, return_photo_id = self._photo_pair(photos)
        findings = self._analyzer.analyze(photos)
        detection_inputs = [
            self._to_detection_input(finding, borrow_photo_id, return_photo_id)
            for finding in findings
        ]
        return create_case(case_id, detection_inputs, policy=self._policy)

    @staticmethod
    def _photo_pair(photos: list[tuple[str, bytes]]) -> tuple[str, str]:
        borrow_ids: list[str] = []
        return_ids: list[str] = []
        for photo_id, _ in photos:
            photo = get_photo_info(photo_id)
            if photo.photo_type == PhotoType.BORROW:
                borrow_ids.append(photo_id)
            elif photo.photo_type == PhotoType.RETURN:
                return_ids.append(photo_id)

        if len(borrow_ids) != 1 or len(return_ids) != 1:
            raise ValueError("photos must contain exactly one borrow photo and one return photo")
        return borrow_ids[0], return_ids[0]

    @staticmethod
    def _to_detection_input(
        finding: AIFinding,
        borrow_photo_id: str,
        return_photo_id: str,
    ) -> DetectionInput:
        if not isinstance(finding, AIFinding):
            raise ValueError("AI analyzer must return only AIFinding objects")
        return DetectionInput(
            detection_id=finding.detection_id,
            borrow_photo_id=borrow_photo_id,
            return_photo_id=return_photo_id,
            source_photo_id=finding.source_photo_id,
            category=finding.category,
            severity=finding.severity,
            confidence=finding.confidence,
        )
