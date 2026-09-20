import pytest

from module_d import ConditionCategory as C, DecisionPolicy, Severity as S, demo_policy


def test_demo_mapping_is_complete_and_category_sensitive():
    policy = demo_policy()
    assert policy.review_confidence_threshold == 0.70
    assert set(policy.priority_score_by_condition) == {(c, s) for c in C for s in S}
    assert policy.priority_score_by_condition == {
        (C.SCRATCH, S.MINOR): 20,
        (C.SCRATCH, S.MODERATE): 45,
        (C.SCRATCH, S.SEVERE): 70,
        (C.COLLISION_DAMAGE, S.MINOR): 50,
        (C.COLLISION_DAMAGE, S.MODERATE): 75,
        (C.COLLISION_DAMAGE, S.SEVERE): 95,
        (C.CLEANLINESS, S.MINOR): 10,
        (C.CLEANLINESS, S.MODERATE): 35,
        (C.CLEANLINESS, S.SEVERE): 60,
    }


@pytest.mark.parametrize("threshold", [0, 0.65, 1])
def test_configurable_threshold(threshold):
    assert DecisionPolicy(demo_policy().priority_score_by_condition, threshold).review_confidence_threshold == threshold


@pytest.mark.parametrize("threshold", [-1, 1.1, float("nan"), float("inf"), True, "0.7", None])
def test_invalid_threshold(threshold):
    with pytest.raises(ValueError):
        DecisionPolicy(demo_policy().priority_score_by_condition, threshold)


@pytest.mark.parametrize("kind", ["missing", "string_key", "bad_key", "string_score", "none"])
def test_invalid_mapping(kind):
    mapping = demo_policy().priority_score_by_condition
    if kind == "missing":
        mapping.pop((C.SCRATCH, S.MINOR))
    elif kind == "string_key":
        mapping.pop((C.SCRATCH, S.MINOR))
        mapping["scratch", "minor"] = 20
    elif kind == "bad_key":
        mapping["unexpected"] = 20
    elif kind == "string_score":
        mapping[C.SCRATCH, S.MINOR] = "50"
    else:
        mapping = None
    with pytest.raises(ValueError):
        DecisionPolicy(mapping)


def test_policy_copies_input_and_demo_instances_are_independent():
    source = demo_policy().priority_score_by_condition
    policy = DecisionPolicy(source)
    source.clear()
    assert len(policy.priority_score_by_condition) == 9
    policy.priority_score_by_condition.clear()
    assert len(demo_policy().priority_score_by_condition) == 9
    with pytest.raises(ValueError):
        policy.validate()


@pytest.mark.parametrize("score", [0, 1, 50, 99, 100])
def test_valid_policy_scores(score):
    mapping = demo_policy().priority_score_by_condition
    mapping[C.SCRATCH, S.MINOR] = score
    assert DecisionPolicy(mapping).priority_score_by_condition[C.SCRATCH, S.MINOR] == score


@pytest.mark.parametrize("score", [-1, 101, 1.5, 50.0, True, False, "50", None])
def test_invalid_policy_scores(score):
    mapping = demo_policy().priority_score_by_condition
    mapping[C.SCRATCH, S.MINOR] = score
    with pytest.raises(ValueError, match="priority score"):
        DecisionPolicy(mapping)


def test_policy_score_validation_rechecks_mutations():
    policy = demo_policy()
    policy.priority_score_by_condition[C.SCRATCH, S.MINOR] = None
    with pytest.raises(ValueError, match="priority score"):
        policy.validate()
