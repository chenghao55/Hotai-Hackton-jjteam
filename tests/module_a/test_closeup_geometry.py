"""Close-up acceptance changes; synthetic detections are not real-photo calibration."""
from copy import deepcopy

import pytest

from module_a import load_config
from module_a.coach_geometry import geometry


def setup(index=0, all_templates=False):
    config = load_config()
    template = config['templates'][index]
    if not all_templates:
        config['templates'] = [template]
    config['calibration_status'] = 'calibrated'  # isolated algorithm test only
    objects = [{'class_id': 0, 'confidence': .99, 'box': [0, 0, 1, 1]}]
    objects += [{'class_id': a['class_id'], 'confidence': .99, 'box': list(a['box'])}
                for a in template['anchors'] if a['required']]
    return config, template, objects


def run(config, template, objects):
    return geometry(objects, template['shot_type'], template['vehicle_type'], None, config)


@pytest.mark.parametrize('index', range(8))
def test_all_closeup_slots_allow_cropped_body_and_one_wheel(index):
    config, template, objects = setup(index)
    assert sum(d['class_id'] == 5 for d in objects) == 1
    assert run(config, template, objects)[0] == 'PASS'
    # An extra cropped distant wheel is not a required feature.
    objects.append({'class_id': 5, 'confidence': .9, 'box': [.96, .3, 1, .5]})
    assert run(config, template, objects)[0] == 'PASS'


@pytest.mark.parametrize(('class_id', 'edge'), [(1, 0), (2, 2), (5, 3)])
def test_detected_required_feature_touching_image_edge_is_accepted(class_id, edge):
    config, template, objects = setup()
    target = next(d for d in objects if d['class_id'] == class_id)
    target['box'][edge] = 0 if edge == 0 else 1
    anchor = next(a for a in template['anchors'] if a['class_id'] == class_id)
    anchor['box'] = list(target['box'])
    assert run(config, template, objects)[0] == 'PASS'


def test_plate_near_edge_is_valid_but_moving_to_frame_center_is_not():
    config, template, objects = setup()
    plate = next(d for d in objects if d['class_id'] == 2)
    assert plate['box'][0] < .15
    assert run(config, template, objects)[0] == 'PASS'
    plate['box'] = [v + .35 if i in (0, 2) else v for i, v in enumerate(plate['box'])]
    assert run(config, template, objects)[0] == 'GEOMETRY_MISMATCH'


def test_cropped_car_box_does_not_rescale_feature_positions():
    config, template, objects = setup()
    assert run(config, template, objects)[0] == 'PASS'
    objects[0]['box'] = [0, .2, .95, .96]
    assert run(config, template, objects)[0] == 'PASS'


def test_short_detected_car_does_not_fail_height_floor():
    config, template, objects = setup()
    objects[0]['box'] = [0, .4, 1, .7]
    code, _, checks = run(config, template, objects)
    assert code == 'PASS'
    assert checks['L3'] == 'pass'


def test_ambiguous_front_and_rear_remain_unconfirmed():
    config, template, objects = setup(all_templates=True)
    # Construct a second angle with the same evidence; calibration may normally
    # separate these templates, but the ambiguity guard must still reject ties.
    config['templates'][2] = deepcopy(template)
    config['templates'][2]['shot_type'] = 'exterior_rear_left'
    assert run(config, template, objects)[0] == 'AMBIGUOUS_TEMPLATES'


def test_uncalibrated_status_does_not_block_matching_geometry():
    config, template, objects = setup(2)
    config['calibration_status'] = 'uncalibrated'
    assert run(config, template, objects)[0] == 'PASS'


def test_local_demo_config_enables_pass_for_matching_template():
    config, template, objects = setup(2)
    assert load_config()['calibration_status'] == 'calibrated'
    assert run(config, template, objects)[0] == 'PASS'


def test_other_car_parts_cannot_complete_target():
    config, template, objects = setup()
    objects[0]['box'] = [.25, .1, 1, .95]
    assert run(config, template, objects)[0] == 'MISSING_REQUIRED_FEATURE'


def test_no_car_and_multiple_cars_still_rejected():
    config, template, objects = setup()
    assert run(config, template, objects[1:])[0] == 'SUBJECT_NOT_DETECTED'
    objects.append(deepcopy(objects[0]))
    assert run(config, template, objects)[0] == 'MULTIPLE_SUBJECTS'
