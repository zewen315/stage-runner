import pytest

from dag import CycleError, UnknownDependencyError, reachable_from, topological_order
from stages import StageRegistry


def names(stages):
    return [s.name for s in stages]


def test_linear_chain_is_ordered_by_dependency():
    registry = StageRegistry()
    registry.import_stage("a", path="a.json")

    @registry.stage("b", depends_on=["a"])
    def b(a):
        return a

    @registry.stage("c", depends_on=["b"])
    def c(b):
        return b

    assert names(topological_order(registry.all())) == ["a", "b", "c"]


def test_independent_branches_both_precede_their_join():
    registry = StageRegistry()
    registry.import_stage("a", path="a.json")
    registry.import_stage("b", path="b.json")

    @registry.stage("join", depends_on=["a", "b"])
    def join(a, b):
        return [a, b]

    ordered = names(topological_order(registry.all()))
    assert ordered.index("a") < ordered.index("join")
    assert ordered.index("b") < ordered.index("join")


def test_cycle_raises():
    registry = StageRegistry()

    @registry.stage("a", depends_on=["b"])
    def a(b):
        return b

    @registry.stage("b", depends_on=["a"])
    def b(a):
        return a

    with pytest.raises(CycleError):
        topological_order(registry.all())


def test_unknown_dependency_raises():
    registry = StageRegistry()

    @registry.stage("a", depends_on=["missing"])
    def a(missing):
        return missing

    with pytest.raises(UnknownDependencyError):
        topological_order(registry.all())


class TestReachableFrom:
    def test_linear_chain_from_the_middle(self):
        registry = StageRegistry()
        registry.import_stage("a", path="a.json")

        @registry.stage("b", depends_on=["a"])
        def b(a):
            return a

        @registry.stage("c", depends_on=["b"])
        def c(b):
            return b

        assert reachable_from(registry.all(), "b") == {"b", "c"}

    def test_from_the_root_includes_everything(self):
        registry = StageRegistry()
        registry.import_stage("a", path="a.json")

        @registry.stage("b", depends_on=["a"])
        def b(a):
            return a

        assert reachable_from(registry.all(), "a") == {"a", "b"}

    def test_from_the_end_is_just_itself(self):
        registry = StageRegistry()
        registry.import_stage("a", path="a.json")

        @registry.stage("b", depends_on=["a"])
        def b(a):
            return a

        assert reachable_from(registry.all(), "b") == {"b"}

    def test_unrelated_branch_is_excluded(self):
        registry = StageRegistry()
        registry.import_stage("a", path="a.json")
        registry.import_stage("x", path="x.json")

        @registry.stage("b", depends_on=["a"])
        def b(a):
            return a

        @registry.stage("y", depends_on=["x"])
        def y(x):
            return x

        assert reachable_from(registry.all(), "b") == {"b"}
        assert reachable_from(registry.all(), "a") == {"a", "b"}

    def test_join_stage_pulls_in_only_its_own_downstream(self):
        registry = StageRegistry()
        registry.import_stage("a", path="a.json")
        registry.import_stage("b", path="b.json")

        @registry.stage("join", depends_on=["a", "b"])
        def join(a, b):
            return [a, b]

        assert reachable_from(registry.all(), "a") == {"a", "join"}
        assert reachable_from(registry.all(), "join") == {"join"}

    def test_unknown_name_raises(self):
        registry = StageRegistry()
        registry.import_stage("a", path="a.json")

        with pytest.raises(UnknownDependencyError):
            reachable_from(registry.all(), "does_not_exist")
