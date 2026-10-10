import io
from dataclasses import replace

import pytest

from module_a import CaptureContext, CaptureSlot, PhotoType, PhotoCoach, load_config


class Detector:
    def __init__(self, detections):
        self.detections = detections
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        return self.detections


@pytest.fixture
def frame():
    # Guidance tests require the optional coach dependencies; CI should install .[coach,test].
    import numpy as np
    from PIL import Image
    y, x = np.indices((256, 256))
    data = np.where((x//4+y//4) % 2, 25, 230).astype('uint8')
    output = io.BytesIO()
    Image.fromarray(data).convert('RGB').save(output, format='PNG')
    return output.getvalue()


@pytest.fixture
def context():
    return CaptureContext(PhotoType.BORROW, CaptureSlot.FRONT_LEFT, 'sedan', 'session-1', 1)


def objects(config):
    t = config['templates'][0]
    return [{'class_id': 0, 'confidence': .99, 'box': t['reference_box']},
            *[{'class_id': a['class_id'], 'confidence': .99, 'box': a['box']}
              for a in t['anchors'] if a['required']]]


def test_calibrated_pass_is_immediate_and_does_not_save(frame, context, tmp_path, monkeypatch):
    import module_a.photo as storage
    monkeypatch.setattr(storage, 'PHOTOS_DIR', tmp_path / 'photos')
    config = load_config()
    config['calibration_status'] = 'calibrated'
    config['templates'] = config['templates'][:1]
    result = PhotoCoach(Detector(objects(config)), config=config).analyze(frame, context)
    assert result.accepted
    assert result.code == result.level == 'PASS'
    assert result.checks['L5'] == 'not_applicable'  # no physical-height claim
    assert not storage.PHOTOS_DIR.exists()


def test_uncalibrated_template_does_not_block_matching_photo(frame, context):
    config = load_config()
    config['calibration_status'] = 'uncalibrated'
    config['templates'] = config['templates'][:1]
    coach = PhotoCoach(Detector(objects(config)), config=config)
    preview = coach.analyze(frame, context)
    final = coach.analyze(frame, replace(context, mode='final', frame_id=2))
    assert preview.accepted and (preview.level, preview.code, preview.action) == ('PASS', 'PASS', 'accept')
    assert preview.message == '照片可提交。'
    assert final.accepted and (final.level, final.code, final.action) == ('PASS', 'PASS', 'accept')
    assert final.checks['L6'] == 'pass'
    assert final.message == '照片可提交。'


def test_shutter_is_always_available_and_final_rechecks(frame, context):
    from PIL import Image
    config = load_config()
    tick = [0.]
    coach = PhotoCoach(Detector(objects(config)), clock=lambda: tick[0])
    first = coach.analyze(frame, context)
    assert not first.accepted
    tick[0] = 20
    second = coach.analyze(frame, replace(context, frame_id=2))
    assert not second.accepted
    assert second.code == 'AMBIGUOUS_TEMPLATES'
    final = coach.analyze(frame, replace(context, mode='final', frame_id=3))
    assert final.action == 'reshoot'
    dark = io.BytesIO()
    Image.new('RGB', (256, 256), 'black').save(dark, format='PNG')
    bad = coach.analyze(dark.getvalue(), replace(context, mode='final', frame_id=4))
    assert bad.code == 'TOO_DARK' and not bad.accepted


def test_quality_priority_and_no_inference(context):
    from PIL import Image
    detector = Detector([])
    for color, expected in [('black', 'TOO_DARK'), ('white', 'OVEREXPOSED'), ('grey', 'LOW_DETAIL')]:
        data = io.BytesIO()
        Image.new('RGB', (128, 128), color).save(data, format='PNG')
        r = PhotoCoach(detector).analyze(data.getvalue(), context)
        assert r.code == expected and not r.accepted
    assert detector.calls == 0


def test_stale_frame_expires_after_preview_gap(frame, context):
    tick = [0.]
    coach = PhotoCoach(Detector(objects(load_config())), clock=lambda: tick[0])
    coach.analyze(frame, context)
    with pytest.raises(ValueError, match='STALE_FRAME'):
        coach.analyze(frame, context)
    tick[0] = 61
    assert coach.analyze(frame, replace(context, frame_id=1)).code == 'AMBIGUOUS_TEMPLATES'


@pytest.mark.parametrize('box,code,level', [
    ([0, .27, .9, .85], 'SUBJECT_NEAR_EDGE', 'L3'),
    ([.4, .4, .6, .6], 'SUBJECT_TOO_SMALL', 'L3'),
    ([.03, .03, .97, .97], 'SUBJECT_TOO_LARGE', 'L3'),
    ([.1, .05, .9, .63], 'OFF_CENTER', 'L4'),
])
def test_distance_and_centering_priority(frame, context, box, code, level):
    # Backward-compatible whole-body mode; current close-up behavior is tested separately.
    config = load_config()
    template = config['templates'][0]
    template.update(allow_body_crop=False, reference_box=[.1, .27, .9, .85],
                    body_width_range=[.6, .93], body_height_range=[.34, .7],
                    body_center_tolerance=[.08, .1])
    r = PhotoCoach(Detector([{'class_id': 0, 'confidence': .99, 'box': box}]), config=config).analyze(frame, context)
    assert (r.code, r.level) == (code, level)


def test_missing_features_never_pass(frame, context):
    detection = objects(load_config())[:1]
    result = PhotoCoach(Detector(detection)).analyze(frame, context)
    assert result.code == 'MISSING_REQUIRED_FEATURE' and result.level == 'L6'
    assert not result.accepted


def test_right_front_remains_a_reshoot_advice_after_waiting(frame, context):
    tick = [0.]
    coach = PhotoCoach(Detector([]), clock=lambda: tick[0])
    context = replace(context, capture_slot=CaptureSlot.INTERIOR_FRONT, entry_side='right')
    assert coach.analyze(frame, context).code == 'FRONT_SEAT_EVIDENCE_UNAVAILABLE'
    tick[0] = 20
    result = coach.analyze(frame, replace(context, frame_id=2))
    assert not result.accepted
    assert result.action == 'reshoot'


def test_unsupported_main_slots_fail_closed(frame, context):
    detector = Detector([])
    result = PhotoCoach(detector).analyze(frame, replace(context, capture_slot=CaptureSlot.FUEL_PARKING_CARD))
    assert result.code == 'UNSUPPORTED_SLOT' and not result.accepted
    assert detector.calls == 0


def test_raw_class_ids_rejected(frame, context):
    with pytest.raises(ValueError, match='INVALID_DETECTION'):
        PhotoCoach(Detector([{'class_id': 6, 'confidence': .9, 'box': [.1, .2, .3, .4]}])).analyze(frame, context)


def test_context_requires_interior_side(context):
    with pytest.raises(ValueError, match='INVALID_ENTRY_SIDE'):
        replace(context, capture_slot=CaptureSlot.INTERIOR_REAR)


@pytest.mark.parametrize('index', range(12))
def test_each_template_uses_its_own_slot_and_door(index):
    from module_a.coach_geometry import geometry
    config = load_config()
    template = config['templates'][index]
    config['templates'] = [template]
    config['calibration_status'] = 'calibrated'
    detections = [{'class_id': a['class_id'], 'confidence': .99, 'box': a['box']}
                  for a in template['anchors'] if a['required']]
    if template['reference_class_id'] is not None:
        detections.append({'class_id': 0, 'confidence': .99, 'box': template['reference_box']})
    code, _, _ = geometry(detections, template['shot_type'],
                             'sedan' if template['vehicle_type'] == 'shared' else template['vehicle_type'],
                             template.get('entry_side'), config)
    assert code == ('FRONT_SEAT_EVIDENCE_UNAVAILABLE' if template.get('evaluation_mode') == 'guide_only' else 'PASS')


def test_missing_near_wheel_cannot_pass(frame, context):
    detections = objects(load_config())
    wheels = [d for d in detections if d['class_id'] == 5]
    detections.remove(wheels[0])
    result = PhotoCoach(Detector(detections)).analyze(frame, context)
    assert result.code == 'MISSING_REQUIRED_FEATURE' and not result.accepted


def test_missing_feature_advice_stays_specific_to_capture_slot(frame, context):
    car = [{'class_id': 0, 'confidence': .99, 'box': [0, 0, 1, 1]}]
    front = PhotoCoach(Detector(car)).analyze(frame, context)
    rear = PhotoCoach(Detector(car)).analyze(frame, replace(context, capture_slot=CaptureSlot.REAR_LEFT))
    interior = PhotoCoach(Detector([])).analyze(frame, replace(
        context, capture_slot=CaptureSlot.INTERIOR_REAR, entry_side='left'))
    assert '前燈' in front.message
    assert '前燈' not in rear.message and '車牌' in rear.message
    assert '輪胎' not in interior.message and '車牌' not in interior.message
