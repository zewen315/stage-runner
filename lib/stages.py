"""Stage definitions and the registry a workflow module builds by calling
`stage`, `import_stage`, and `export_stage` on its own StageRegistry.

Three kinds, deliberately different shapes:
- "stage": pure Python logic. Takes upstream values as arguments, returns a
  new value. Never touches the filesystem or network -- fully unit-testable
  with plain values.
- "import": the only place external input enters the system. No function,
  no dependencies -- just a name and a file path to read.
- "export": the only place a result leaves the system. No function, no
  downstream resource -- just a name, the one resource it depends on, and
  a file path to write.

Keeping import/export generic and function-less means only two small,
reusable pieces of code ever do file I/O; every "stage" a user writes is
pure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Kind = Literal["stage", "import", "export"]


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

    def export_stage(self, name: str, depends_on: str, path: str) -> None:
        self._stages[name] = StageDef(
            name=name, kind="export", depends_on=[depends_on], path=path
        )

    def get(self, name: str) -> StageDef:
        return self._stages[name]

    def all(self) -> list[StageDef]:
        return list(self._stages.values())
