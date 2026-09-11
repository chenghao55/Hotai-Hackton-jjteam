import pytest

from module_d import ConditionCategory as C, DecisionPolicy, Priority, Severity as S, demo_policy


def test_demo_mapping_is_complete_and_category_sensitive():
    policy = demo_policy()
    assert policy.review_confidence_threshold == 0.70
    assert set(policy.priority_by_condition) == {(c, s) for c in C for s in S}
    assert policy.priority_by_condition[C.SCRATCH, S.MINOR] == Priority.LOW
    assert policy.priority_by_condition[C.COLLISION_DAMAGE, S.MINOR] == Priority.MEDIUM


@pytest.mark.parametrize("threshold", [0, 0.65, 1])
def test_configurable_threshold(threshold):
    assert DecisionPolicy(demo_policy().priority_by_condition, threshold).review_confidence_threshold == threshold


@pytest.mark.parametrize("threshold", [-1, 1.1, float("nan"), float("inf"), True, "0.7", None])
def test_invalid_threshold(threshold):
    with pytest.raises(ValueError):
        DecisionPolicy(demo_policy().priority_by_condition, threshold)


@pytest.mark.parametrize("kind", ["missing", "string_key", "bad_key", "string_priority", "none"])
def test_invalid_mapping(kind):
    mapping = demo_policy().priority_by_condition
    if kind == "missing":
        mapping.pop((C.SCRATCH, S.MINOR))
    elif kind == "string_key":
        mapping.pop((C.SCRATCH, S.MINOR))
        mapping["scratch", "minor"] = Priority.LOW
    elif kind == "bad_key":
        mapping["unexpected"] = Priority.LOW
    elif kind == "string_priority":
        mapping[C.SCRATCH, S.MINOR] = "low"
    else:
        mapping = None
    with pytest.raises(ValueError):
        DecisionPolicy(mapping)


def test_policy_copies_input_and_demo_instances_are_independent():
    source = demo_policy().priority_by_condition
    policy = DecisionPolicy(source)
    source.clear()
    assert len(policy.priority_by_condition) == 9
    policy.priority_by_condition.clear()
    assert len(demo_policy().priority_by_condition) == 9
    with pytest.raises(ValueError):
        policy.validate()
