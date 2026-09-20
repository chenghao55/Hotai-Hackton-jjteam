from pathlib import Path

import pytest

from module_a import Photo, PhotoType
from module_b import AIFinding, AIAnalyzer, CaseBuildingModuleB, ModuleB, NoDetectionsAnalyzer
from module_d import Case, ConditionCategory as C, DetectionInput, ReviewState as R, Severity as S, demo_policy


def photo_info(photo_id: str, photo_type: PhotoType) -> Photo:
    return Photo(photo_id, photo_type, "image/jpeg", Path(f"{photo_id}.bin"))


@pytest.fixture
def photo_lookup(monkeypatch):
    types = {
        "return-photo": PhotoType.RETURN,
        "borrow-photo": PhotoType.BORROW,
    }

    def lookup(photo_id: str) -> Photo:
        return photo_info(photo_id, types[photo_id])

    monkeypatch.setattr("module_b.orchestrator.get_photo_info", lookup)


class FakeAnalyzer(AIAnalyzer):
    def __init__(self, findings: list[AIFinding]) -> None:
        self.findings = findings
        self.received_photos: list[tuple[str, bytes]] | None = None

    def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
        self.received_photos = photos
        return self.findings


def sample_photos() -> list[tuple[str, bytes]]:
    # Deliberately return-first: Module B must use Module A metadata, not list order.
    return [("return-photo", b"return"), ("borrow-photo", b"borrow")]


def test_module_b_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ModuleB()


def test_ai_analyzer_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        AIAnalyzer()


def test_no_detections_analyzer_returns_empty_findings():
    assert NoDetectionsAnalyzer().analyze(sample_photos()) == []


def test_orchestrator_returns_case_for_no_detections(photo_lookup):
    module_b = CaseBuildingModuleB(NoDetectionsAnalyzer(), policy=demo_policy())

    case = module_b.analyze("case-empty", sample_photos())

    assert isinstance(case, Case)
    assert case.case_id == "case-empty"
    assert case.detections == []
    assert case.priority_score is None


def test_orchestrator_converts_findings_and_calls_module_d(photo_lookup, monkeypatch):
    analyzer = FakeAnalyzer([
        AIFinding("d1", C.COLLISION_DAMAGE, S.SEVERE, 0.9),
        AIFinding("d2", C.SCRATCH, S.MINOR, 0.2),
    ])
    captured: dict[str, object] = {}

    def fake_create_case(case_id, detections, *, policy):
        captured["case_id"] = case_id
        captured["detections"] = detections
        captured["policy"] = policy
        return Case(case_id)

    monkeypatch.setattr("module_b.orchestrator.create_case", fake_create_case)
    policy = demo_policy()
    case = CaseBuildingModuleB(analyzer, policy=policy).analyze("case-1", sample_photos())

    assert case.case_id == "case-1"
    assert analyzer.received_photos == sample_photos()
    assert captured["case_id"] == "case-1"
    assert captured["policy"] is policy
    assert captured["detections"] == [
        DetectionInput("d1", "borrow-photo", "return-photo", C.COLLISION_DAMAGE, S.SEVERE, 0.9),
        DetectionInput("d2", "borrow-photo", "return-photo", C.SCRATCH, S.MINOR, 0.2),
    ]


def test_module_d_decides_review_state_and_priority(photo_lookup):
    analyzer = FakeAnalyzer([
        AIFinding("accepted", C.COLLISION_DAMAGE, S.SEVERE, 0.9),
        AIFinding("review", C.SCRATCH, S.MINOR, 0.2),
    ])

    case = CaseBuildingModuleB(analyzer, policy=demo_policy()).analyze("case-1", sample_photos())

    assert [d.review_state for d in case.detections] == [R.AUTO_ACCEPTED, R.NEEDS_REVIEW]
    assert case.priority_score == 95
    assert case.status.value == "unassigned"
    assert case.payment_amount == 0


def test_analyzer_error_does_not_create_or_return_a_case(photo_lookup, monkeypatch):
    class FailingAnalyzer(AIAnalyzer):
        def analyze(self, photos: list[tuple[str, bytes]]) -> list[AIFinding]:
            raise RuntimeError("AI unavailable")

    create_case_called = False

    def fake_create_case(*args, **kwargs):
        nonlocal create_case_called
        create_case_called = True
        raise AssertionError("create_case must not be called")

    monkeypatch.setattr("module_b.orchestrator.create_case", fake_create_case)
    module_b = CaseBuildingModuleB(FailingAnalyzer(), policy=demo_policy())

    with pytest.raises(RuntimeError, match="AI unavailable"):
        module_b.analyze("case-1", sample_photos())

    assert not create_case_called


def test_orchestrator_rejects_missing_photo_type_before_analyzing(photo_lookup):
    analyzer = FakeAnalyzer([])
    module_b = CaseBuildingModuleB(analyzer, policy=demo_policy())

    with pytest.raises(ValueError, match="exactly one borrow"):
        module_b.analyze("case-1", [("borrow-photo", b"borrow")])

    assert analyzer.received_photos is None
