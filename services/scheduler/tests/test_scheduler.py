"""Scheduler owns DAG order and run status only -- it never touches a
ResourceClient (that's the Runner's job, tested separately in
test_runner.py). These tests use a bare recording stand-in for Runner so
Scheduler's own logic is verified in isolation.
"""

from stages import StageRegistry
from scheduler import Scheduler


class RecordingRunner:
    def __init__(self, fail_on: str | None = None):
        self.ran: list[str] = []
        self._fail_on = fail_on

    def run(self, stage_def) -> None:
        if stage_def.name == self._fail_on:
            raise ValueError("bad data")
        self.ran.append(stage_def.name)


def _linear_registry() -> StageRegistry:
    registry = StageRegistry()
    registry.import_stage("a", path="a.json")

    @registry.stage("b", depends_on=["a"])
    def b(a):
        return a

    @registry.stage("c", depends_on=["b"])
    def c(b):
        return b

    return registry


def test_runs_stages_in_dependency_order():
    runner = RecordingRunner()

    result = Scheduler(_linear_registry(), runner).run()

    assert runner.ran == ["a", "b", "c"]
    assert result.completed == ["a", "b", "c"]
    assert result.failed is None


def test_a_failing_stage_stops_the_run_and_skips_downstream():
    runner = RecordingRunner(fail_on="b")

    result = Scheduler(_linear_registry(), runner).run()

    assert runner.ran == ["a"]
    assert result.completed == ["a"]
    assert result.failed == "b"
    assert isinstance(result.error, ValueError)
