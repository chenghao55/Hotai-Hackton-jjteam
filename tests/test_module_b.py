import pytest

from module_b import ModuleB
from module_d.models import Case


def test_module_b_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ModuleB()


def test_fake_module_b_accepts_photos_and_returns_case():
    class FakeModuleB(ModuleB):
        def analyze(self, case_id: str, photos: list[tuple[str, bytes]]) -> Case:
            assert photos == [
                ("borrow-photo", b"borrow-image"),
                ("return-photo", b"return-image"),
            ]
            return Case(case_id)

    case = FakeModuleB().analyze(
        "case-1",
        [("borrow-photo", b"borrow-image"), ("return-photo", b"return-image")],
    )

    assert isinstance(case, Case)
    assert case.case_id == "case-1"
