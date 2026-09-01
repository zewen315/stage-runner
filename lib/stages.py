"""Stage definitions and the registry a workflow module builds by calling
`stage` and `import_stage` on its own StageRegistry.

Two kinds, deliberately different shapes:
- "stage": pure Python logic. Takes upstream values as arguments, returns a
  new value. Never touches the filesystem or network -- fully unit-testable
  with plain values. Every stage's output is a resource, including the
  last one in a workflow -- there's no separate notion of a run's "final
  output" leaving the system some other way.
- "import": the only place external input enters the system. No function,
  no dependencies -- just a name and a file path to read.

Keeping import generic and function-less means only one small, reusable
piece of code ever does file I/O; every "stage" a user writes is pure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Kind = Literal["stage", "import"]


@dataclass(frozen=True)
class StageDef:
    name: str
    kind: Kind
    depends_on: list[str] = field(default_factory=list)
    fn: Callable[..., Any] | None = None
    path: str | None = None


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
            self._stages[name] = StageDef(
                name=name, kind="stage", depends_on=list(depends_on), fn=fn
            )
            return fn

        return decorator

    def import_stage(self, name: str, path: str) -> None:
        self._stages[name] = StageDef(name=name, kind="import", path=path)

    def get(self, name: str) -> StageDef:
        return self._stages[name]

    def all(self) -> list[StageDef]:
        return list(self._stages.values())
