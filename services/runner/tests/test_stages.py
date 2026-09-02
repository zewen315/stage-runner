"""Direct unit tests for StageRegistry/StageDef (lib/stages.py) -- used
throughout the other test suites as a fixture helper, but never tested
as a unit in its own right."""

import pytest

from stages import StageRegistry


def test_stage_registers_with_defaults():
    registry = StageRegistry()

    @registry.stage("a")
    def a():
        return 1

    stage_def = registry.get("a")
    assert stage_def.name == "a"
    assert stage_def.fn is a
    assert stage_def.depends_on == []
    assert stage_def.retries == 0


def test_stage_records_depends_on_and_retries():
    registry = StageRegistry()

    @registry.stage("b", depends_on=["a"], retries=3)
    def b(a):
        return a

    stage_def = registry.get("b")
    assert stage_def.depends_on == ["a"]
    assert stage_def.retries == 3


def test_stage_decorator_returns_the_original_function_unchanged():
    registry = StageRegistry()

    @registry.stage("a")
    def a():
        return 42

    assert a() == 42


def test_all_returns_every_registered_stage():
    registry = StageRegistry()
    registry.stage("a")(lambda: None)
    registry.stage("b", depends_on=["a"])(lambda a: a)

    assert {s.name for s in registry.all()} == {"a", "b"}


def test_get_unknown_stage_raises_key_error():
    registry = StageRegistry()
    with pytest.raises(KeyError):
        registry.get("does_not_exist")


def test_re_registering_the_same_name_overwrites_it():
    registry = StageRegistry()
    registry.stage("a")(lambda: 1)
    registry.stage("a")(lambda: 2)

    assert len(registry.all()) == 1
    assert registry.get("a").fn() == 2


def test_on_failure_defaults_to_halt():
    assert StageRegistry().on_failure == "halt"


def test_on_failure_fallback_is_recorded():
    assert StageRegistry(on_failure="fallback").on_failure == "fallback"
