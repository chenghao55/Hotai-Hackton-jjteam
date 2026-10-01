"""Draft box geometry; scores are errors, not angle or height measurements."""
from itertools import permutations
from math import hypot, sqrt, isfinite


def features(box, ref):
    x, y, r, b = box
    w, h = ref[2] - ref[0], ref[3] - ref[1]
    return ((x + r - 2 * ref[0]) / (2 * w), (y + b - 2 * ref[1]) / (2 * h),
            (r - x) / w, (b - y) / h)


def score(template, objects, ref, thresholds):
    required = [a for a in template['anchors'] if a['required']]
    if len(required) < template['min_valid_features'] or not required:
        return None
    matches = {}
    for cls in {a['class_id'] for a in required}:
        anchors = [a for a in required if a['class_id'] == cls]
        candidates = sorted((d for d in objects if d['class_id'] == cls),
                            key=lambda d: -d['confidence'])[:8]
        if len(candidates) < len(anchors):
            return None
        best = None
        for choice in permutations(candidates, len(anchors)):
            errors = [sqrt(sum(((v - t) / tol) ** 2 for v, t, tol in
                      zip(features(d['box'], ref), features(a['box'], template['reference_box']),
                          a['tolerance'])) / 4) for a, d in zip(anchors, choice)]
            cost = sum(e * e for e in errors)
            if best is None or cost < best[0]:
                best = (cost, choice, errors)
        for a, d, e in zip(anchors, best[1], best[2]):
            matches[a['id']] = (a, d, e)
    errors = [m[2] for m in matches.values()]
    for left, right in template['relationships']:
        a, b = matches[left], matches[right]
        observed = [x - y for x, y in zip(features(a[1]['box'], ref)[:2], features(b[1]['box'], ref)[:2])]
        expected = [x - y for x, y in zip(features(a[0]['box'], template['reference_box'])[:2],
                                         features(b[0]['box'], template['reference_box'])[:2])]
        errors.append(sqrt(sum(((observed[k] - expected[k]) /
                      hypot(a[0]['tolerance'][k], b[0]['tolerance'][k])) ** 2 for k in (0, 1)) / 2))
    error = sqrt(sum(e * e for e in errors) / len(errors))
    return error, error <= thresholds['max_match_error'] and max(errors) <= thresholds['max_per_anchor_error']


def geometry(detections, slot, vehicle_type, entry_side, config):
    for d in detections:
        box = d['box']
        if (type(d['class_id']) is not int or str(d['class_id']) not in config['model_classes']
                or not isfinite(d['confidence']) or not 0 <= d['confidence'] <= 1
                or len(box) != 4 or any(not isfinite(v) or not 0 <= v <= 1 for v in box)
                or box[2] <= box[0] or box[3] <= box[1]):
            raise ValueError('INVALID_DETECTION')
    objects = [d for d in detections if d['confidence'] >= config['thresholds']['detection_confidence']]
    templates = [t for t in config['templates'] if t['vehicle_type'] in (vehicle_type, 'shared') and
                 (t['shot_type'].startswith('exterior_') if slot.startswith('exterior_') else
                  t['shot_type'] == slot and t.get('entry_side') == entry_side)]
    checks = {'L3': 'not_applicable', 'L4': 'not_applicable', 'L5': 'not_evaluated', 'L6': 'not_evaluated'}
    def stop(code, level):
        if level:
            checks[level] = 'unknown' if code in ('TEMPLATE_NOT_CALIBRATED', 'FRONT_SEAT_EVIDENCE_UNAVAILABLE') else 'fail'
        return code, level, checks
    target = next((t for t in templates if t['shot_type'] == slot), None)
    if target is None:
        if slot in ('interior_front', 'interior_rear'):
            return stop('FRONT_SEAT_EVIDENCE_UNAVAILABLE', 'L6')
        return stop('UNSUPPORTED_SLOT', 'L6')
    if target.get('evaluation_mode') == 'guide_only':
        return stop('FRONT_SEAT_EVIDENCE_UNAVAILABLE', 'L6')
    ref = [0, 0, 1, 1]
    if target['reference_class_id'] is not None:
        cars = [d for d in objects if d['class_id'] == 0]
        if len(cars) != 1:
            return stop('SUBJECT_NOT_DETECTED' if not cars else 'MULTIPLE_SUBJECTS', 'L3')
        ref = cars[0]['box']
        x, y, r, b = ref
        margin = target['edge_margin']
        if min(x, y, 1-r, 1-b) < margin:
            return stop('SUBJECT_NEAR_EDGE', 'L3')
        w, h = r-x, b-y
        if w < target['body_width_range'][0] or h < target['body_height_range'][0]:
            return stop('SUBJECT_TOO_SMALL', 'L3')
        if w > target['body_width_range'][1] or h > target['body_height_range'][1]:
            return stop('SUBJECT_TOO_LARGE', 'L3')
        checks['L3'] = 'pass'
        expected = target['reference_box']
        if any(abs((ref[k] + ref[k+2] - expected[k] - expected[k+2]) / 2) >
               target['body_center_tolerance'][k] for k in (0, 1)):
            return stop('OFF_CENTER', 'L4')
        checks['L4'] = 'pass'
        def inside(d):
            a, c, e, f = d['box']
            return max(0, min(e, r)-max(a, x))*max(0, min(f, b)-max(c, y))/((e-a)*(f-c))
        objects = [d for d in objects if inside(d) >= config['thresholds']['association_fraction']]
    # L5 physical camera height is not observable from these boxes; never invent it.
    checks['L5'] = 'not_applicable'
    scores = [(t['shot_type'], score(t, objects, ref, config['thresholds'])) for t in templates]
    requested = next(s for name, s in scores if name == slot)
    if requested is None:
        return stop('MISSING_REQUIRED_FEATURE', 'L6')
    ranked = sorted(((name, s) for name, s in scores if s is not None), key=lambda item: item[1][0])
    distinct = len(ranked) == 1 or ranked[1][1][0] - ranked[0][1][0] >= config['thresholds']['min_runner_up_gap']
    if distinct and ranked[0][1][1] and ranked[0][0] != slot:
        return stop('POSSIBLE_WRONG_SLOT', 'L6')
    if not requested[1]:
        return stop('GEOMETRY_MISMATCH', 'L6')
    if not distinct:
        return stop('AMBIGUOUS_TEMPLATES', 'L6')
    if config['calibration_status'] != 'calibrated':
        return stop('TEMPLATE_NOT_CALIBRATED', 'L6')
    checks['L6'] = 'pass'
    return 'PASS', 'PASS', checks
