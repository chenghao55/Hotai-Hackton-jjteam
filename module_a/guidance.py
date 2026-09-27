"""Python shooting guidance. No HTTP, storage, case creation or review dispatch."""
from dataclasses import dataclass, field
from pathlib import Path
from collections import OrderedDict
from threading import Lock
import json
import time

from .photo import CaptureSlot, PhotoType
from .coach_image import decode, quality
from .coach_geometry import geometry

SLOTS = {CaptureSlot.FRONT_LEFT: 'exterior_front_left', CaptureSlot.FRONT_RIGHT: 'exterior_front_right',
         CaptureSlot.REAR_LEFT: 'exterior_rear_left', CaptureSlot.REAR_RIGHT: 'exterior_rear_right',
         CaptureSlot.INTERIOR_FRONT: 'interior_front', CaptureSlot.INTERIOR_REAR: 'interior_rear'}


def load_config():
    return json.loads(Path(__file__).with_name('capture_templates.json').read_text(encoding='utf-8'))


@dataclass(frozen=True)
class CaptureContext:
    photo_type: PhotoType
    capture_slot: CaptureSlot
    vehicle_type: str
    session_id: str
    frame_id: int
    entry_side: str | None = None
    mode: str = 'preview'
    image_mirrored: bool = False
    source: str = 'camera_raw'

    def __post_init__(self):
        if not isinstance(self.photo_type, PhotoType) or not isinstance(self.capture_slot, CaptureSlot):
            raise ValueError('INVALID_PHOTO_METADATA')
        if self.vehicle_type not in ('sedan', 'suv') or self.mode not in ('preview', 'final'):
            raise ValueError('INVALID_CAPTURE_CONTEXT')
        if not isinstance(self.session_id, str) or not self.session_id.strip() or len(self.session_id) > 128:
            raise ValueError('INVALID_SESSION_ID')
        if type(self.frame_id) is not int or self.frame_id < 0:
            raise ValueError('INVALID_FRAME_ID')
        interior = self.capture_slot in (CaptureSlot.INTERIOR_FRONT, CaptureSlot.INTERIOR_REAR)
        if (interior and self.entry_side not in ('left', 'right')) or (not interior and self.entry_side is not None):
            raise ValueError('INVALID_ENTRY_SIDE')
        if self.image_mirrored is not False or self.source != 'camera_raw':
            raise ValueError('RAW_UNMIRRORED_IMAGE_REQUIRED')


@dataclass(frozen=True)
class GuidanceResult:
    accepted: bool
    level: str
    code: str
    message: str
    action: str
    can_capture: bool = False
    review_required: bool = False
    checks: dict = field(default_factory=dict)
    manual_review_remaining_ms: int | None = None
    rules_version: str = ''


MESSAGES = {
    'TOO_DARK': '光線不足，請移到較明亮的位置。', 'OVEREXPOSED': '畫面過亮，請調整曝光。',
    'BACKLIGHT': '車身比背景暗，請調整站位或曝光。', 'BLUR': '請拿穩手機並重新對焦。',
    'LOW_DETAIL': '無法確認清晰度，請將拍攝主體清楚放入畫面。',
    'SUBJECT_NOT_DETECTED': '請將目標車輛放入畫面。', 'MULTIPLE_SUBJECTS': '請只拍攝目標車輛。',
    'SUBJECT_NEAR_EDGE': '請保留完整車身與輪胎。', 'SUBJECT_TOO_SMALL': '請稍微靠近。',
    'SUBJECT_TOO_LARGE': '請稍微後退。', 'OFF_CENTER': '請將車身移至取景框中央。',
    'POSSIBLE_WRONG_SLOT': '請確認目前指定的車角。', 'PASS': '構圖與畫質符合要求，可以拍照。',
    'TEMPLATE_NOT_CALIBRATED': '基準尚待照片校正，稍後可拍照交人工確認。',
    'FRONT_SEAT_EVIDENCE_UNAVAILABLE': '請拍入前排椅背與坐墊；目前模型無法確認前排完整。',
    'UNSUPPORTED_SLOT': '目前教練尚未支援此拍攝槽位。',
}


class PhotoCoach:
    def __init__(self, detector, *, config=None, clock=time.monotonic):
        self.detector = detector
        self.config = config if config is not None else load_config()
        self.clock = clock
        self.sessions = OrderedDict()
        self.lock = Lock()

    def analyze(self, image: bytes, context: CaptureContext) -> GuidanceResult:
        # Serialize session updates and inference so older frames cannot overwrite newer advice.
        with self.lock:
            return self._analyze(image, context)

    def _analyze(self, raw, context):
        if not isinstance(context, CaptureContext):
            raise ValueError('CAPTURE_CONTEXT_REQUIRED')
        checks = {f'L{i}': 'not_evaluated' for i in range(1, 7)}
        def result(code, level, *, manual=False, remaining=None):
            accepted = code == 'PASS'
            return GuidanceResult(accepted, level, code,
                '可以先拍照，照片須交由人工審理。' if manual else MESSAGES.get(code, '請依示意圖調整構圖。'),
                'human_review' if manual else 'accept' if accepted else 'reshoot',
                accepted or manual, manual, dict(checks), remaining, self.config['version'])
        if context.capture_slot not in SLOTS:
            return result('UNSUPPORTED_SLOT', 'L6')
        image = decode(raw)
        now = self.clock()
        key = (context.session_id, context.photo_type, context.capture_slot, context.vehicle_type, context.entry_side)
        old = self.sessions.get(key)
        if context.mode == 'preview':
            if old and context.frame_id <= old[2]:
                raise ValueError('STALE_FRAME')
            start = old[0] if old and now-old[1] <= 60 else now
            old = (start, now, context.frame_id)
            self.sessions[key] = old
            self.sessions.move_to_end(key)
            if len(self.sessions) > 2000:
                self.sessions.popitem(last=False)
        q = quality(image)
        checks['L1'] = 'fail'
        if q['mean'] < 50 and q['dark'] > .65:
            return result('TOO_DARK', 'L1')
        if q['mean'] > 225 and q['bright'] > .78:
            return result('OVEREXPOSED', 'L1')
        checks['L1'], checks['L2'] = 'pass', 'fail'
        if q['sharpness'] < 45:
            if q['sharpness'] < 12:
                checks['L2'] = 'unknown'
            return result('LOW_DETAIL' if q['sharpness'] < 12 else 'BLUR', 'L2')
        checks['L2'] = 'pass'
        detections = self.detector.predict(image)
        if not isinstance(detections, list) or len(detections) > 200:
            raise ValueError('INVALID_DETECTIONS')
        code, level, geometry_checks, eligible = geometry(detections, SLOTS[context.capture_slot],
                                                         context.vehicle_type, context.entry_side, self.config)
        cars = [d for d in detections if d['class_id'] == 0 and
                d['confidence'] >= self.config['thresholds']['detection_confidence']]
        if len(cars) == 1:
            subject = quality(image, cars[0]['box'])
            if subject['mean'] < 72 and q['mean']-subject['mean'] > 70 and subject['dark'] > .42:
                checks['L1'] = 'fail'
                return result('BACKLIGHT', 'L1')
        checks.update(geometry_checks)
        remaining = None
        if eligible:
            elapsed = max(0, (now-old[0])*1000) if old and now-old[1] <= 60 else 0
            remaining = max(0, int(self.config['manual_review_after_ms']-elapsed))
        return result(code, level, manual=eligible and remaining == 0, remaining=remaining)
