import pytest

from dag import CycleError, UnknownDependencyError, reachable_from, topological_order
from stages import StageRegistry


def names(stages):
    return [s.name for s in stages]


def _root(registry, name):
    """A registered stage with no dependencies -- standing in for
    whatever real logic a root stage would run; these tests only care
    about DAG shape, not stage behavior."""
    registry.stage(name)(lambda: None)


def test_linear_chain_is_ordered_by_dependency():
    registry = StageRegistry()
    _root(registry, "a")

    @registry.stage("b", depends_on=["a"])
    def b(a):
        return a

    @registry.stage("c", depends_on=["b"])
    def c(b):
        return b

    assert names(topological_order(registry.all())) == ["a", "b", "c"]


def test_independent_branches_both_precede_their_join():
    registry = StageRegistry()
    _root(registry, "a")
    _root(registry, "b")

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


def test_dependency_on_an_unregistered_name_is_not_an_error():
    """A dependency with no registered stage is an external resource,
    expected to already exist in the Resource Store (e.g. a workflow's
    injected root) -- not a DAG configuration error. It's just not a
    stage to order."""
    registry = StageRegistry()

    @registry.stage("a", depends_on=["injected"])
    def a(injected):
        return injected

    assert names(topological_order(registry.all())) == ["a"]


class TestReachableFrom:
    def test_linear_chain_from_the_middle(self):
        registry = StageRegistry()
        _root(registry, "a")

        @registry.stage("b", depends_on=["a"])
        def b(a):
            return a

        @registry.stage("c", depends_on=["b"])
        def c(b):
            return b

        assert reachable_from(registry.all(), "b") == {"b", "c"}

    def test_from_the_root_includes_everything(self):
        registry = StageRegistry()
        _root(registry, "a")

        @registry.stage("b", depends_on=["a"])
        def b(a):
            return a

        assert reachable_from(registry.all(), "a") == {"a", "b"}

    def test_from_the_end_is_just_itself(self):
        registry = StageRegistry()
        _root(registry, "a")

        @registry.stage("b", depends_on=["a"])
        def b(a):
            return a

        assert reachable_from(registry.all(), "b") == {"b"}

    def test_unrelated_branch_is_excluded(self):
        registry = StageRegistry()
        _root(registry, "a")
        _root(registry, "x")

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
        _root(registry, "a")
        _root(registry, "b")

        @registry.stage("join", depends_on=["a", "b"])
        def join(a, b):
            return [a, b]

        assert reachable_from(registry.all(), "a") == {"a", "join"}
        assert reachable_from(registry.all(), "join") == {"join"}

    def test_unknown_name_raises(self):
        registry = StageRegistry()
        _root(registry, "a")

        with pytest.raises(UnknownDependencyError):
            reachable_from(registry.all(), "does_not_exist")

    def test_unregistered_dependency_does_not_appear_in_the_result(self):
        registry = StageRegistry()

        @registry.stage("a", depends_on=["injected"])
        def a(injected):
            return injected

        assert reachable_from(registry.all(), "a") == {"a"}
