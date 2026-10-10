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


@pytest.mark.parametrize('class_id', [1, 2, 5])
def test_required_feature_must_not_be_cut_off(class_id):
    config, template, objects = setup()
    target = next(d for d in objects if d['class_id'] == class_id)
    target['box'][0] = 0
    assert run(config, template, objects)[0] == 'MISSING_REQUIRED_FEATURE'


def test_plate_near_edge_is_valid_but_moving_to_frame_center_is_not():
    config, template, objects = setup()
    plate = next(d for d in objects if d['class_id'] == 2)
    assert .05 < plate['box'][0] < .06
    assert run(config, template, objects)[0] == 'PASS'
    plate['box'] = [v + .35 if i in (0, 2) else v for i, v in enumerate(plate['box'])]
    assert run(config, template, objects)[0] == 'GEOMETRY_MISMATCH'


def test_cropped_car_box_does_not_rescale_feature_positions():
    config, template, objects = setup()
    assert run(config, template, objects)[0] == 'PASS'
    objects[0]['box'] = [0, .2, .95, .96]
    assert run(config, template, objects)[0] == 'PASS'


def test_ambiguous_front_and_rear_remain_unconfirmed():
    config, template, objects = setup(all_templates=True)
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
