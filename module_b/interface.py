"""Abstract contract for image analysis implementations."""

from abc import ABC, abstractmethod

from module_d.models import Case

class ModuleB(ABC):
    """Analyzes supplied photos and returns a Case created through Module D."""

    @abstractmethod
    def analyze(
        self,
        case_id: str,
        photos: list[tuple[str, bytes]],
    ) -> Case:
        raise NotImplementedError
