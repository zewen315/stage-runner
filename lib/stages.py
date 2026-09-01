"""Stage definitions and the registry a workflow module builds by calling
`stage` on its own StageRegistry.

A stage is pure Python logic: it takes upstream values as arguments and
returns a new value, never touching the filesystem or network -- fully
unit-testable with plain values. Every stage's output is a resource,
including a workflow's first and last stages -- there's no special
"external input enters here" or "the result leaves here" stage kind.
A stage with no dependencies (a workflow's root) expects its own resource
to already exist in the Resource Store; nothing runs to produce it. See
`cli/stagerunner.py`'s `resource upload` command for injecting one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass(frozen=True)
class StageDef:
    name: str
    fn: Callable[..., Any]
    depends_on: list[str] = field(default_factory=list)


FailurePolicy = Literal["halt", "fallback"]


class StageRegistry:
    """One registry per workflow module -- no hidden global state, so
    multiple workflows (or the same workflow in multiple tests) never
    collide.

    `on_failure` governs what the Scheduler does when a stage in this
    workflow fails: "halt" (default) stops the run there, nothing
    downstream ever dispatches. "fallback" keeps going, treating the
    failed stage as if it had produced its currently-promoted resource
    version instead -- degrades to "halt" for a run where no such version
    exists yet (nothing to fall back to)."""

    def __init__(self, on_failure: FailurePolicy = "halt") -> None:
        self._stages: dict[str, StageDef] = {}
        self.on_failure = on_failure

    def stage(self, name: str, depends_on: list[str] = ()):
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._stages[name] = StageDef(name=name, fn=fn, depends_on=list(depends_on))
            return fn

        return decorator

    def get(self, name: str) -> StageDef:
        return self._stages[name]

    def all(self) -> list[StageDef]:
        return list(self._stages.values())
