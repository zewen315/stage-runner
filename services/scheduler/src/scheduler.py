"""Decides *what* runs next -- resolves a StageRegistry into dependency
order and walks it, tracking run status. Doesn't touch the Resource Store
itself; that's the Runner's job (see runner.py). A stage that raises stops
the run there -- its resource is never uploaded/promoted, so nothing
downstream sees a partial or broken result. That's the hook automatic
rollback and manual failure-injection build on next.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dag import topological_order
from runner import Runner
from stages import StageRegistry


@dataclass
class RunResult:
    completed: list[str] = field(default_factory=list)
    failed: str | None = None
    error: Exception | None = None


class Scheduler:
    def __init__(self, registry: StageRegistry, runner: Runner):
        self._registry = registry
        self._runner = runner

    def run(self) -> RunResult:
        order = topological_order(self._registry.all())
        result = RunResult()

        for stage_def in order:
            try:
                self._runner.run(stage_def)
            except Exception as exc:  # noqa: BLE001 -- deliberately stop the run, not crash the process
                result.failed = stage_def.name
                result.error = exc
                return result
            result.completed.append(stage_def.name)

        return result
