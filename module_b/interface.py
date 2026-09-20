"""Abstract contract for image analysis implementations."""

from abc import ABC, abstractmethod

from module_d.models import Case

# TODO: 鄭宇勳 analyze 將photo_id, 圖片檔傳給AI
# 見 module_b\photo.py _load_photo 可透過id取得Photo class
# 見 module_d\logic.py .create_case 建完detections 時呼叫這個 建立case
# 見 module_d\models.py .DetectionInput 這是create_case 要求的輸入模板
class ModuleB(ABC):
    """Analyzes supplied photos and returns a Case created through Module D."""

    @abstractmethod
    def analyze(
        self,
        case_id: str,
        photos: list[tuple[str, bytes]],
    ) -> Case:
        raise NotImplementedError
