"""Topological ordering of a StageRegistry's stages, by `depends_on`.

A `depends_on` name that isn't itself a registered stage is an external
dependency -- a resource with no stage that produces it, expected to
already exist in the Resource Store (injected directly; see `resource
upload` in the CLI). Neither function here treats that as an error: it's
simply not a stage to order or walk into. Resolving it against the
Resource Store's current version is the Scheduler's job (poller.py), not
this module's -- this module only knows about stages, never the Resource
Store.
"""

from __future__ import annotations

from stages import StageDef


class CycleError(Exception):
    """Raised when the stage graph has a dependency cycle."""


class UnknownDependencyError(Exception):
    """Raised when `start_from` names something that isn't a registered
    stage."""


def topological_order(stages: list[StageDef]) -> list[StageDef]:
    by_name = {s.name: s for s in stages}

    visited: set[str] = set()
    in_progress: set[str] = set()
    ordered: list[StageDef] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in in_progress:
            raise CycleError(f"dependency cycle detected at {name!r}")

        in_progress.add(name)
        for dep in by_name[name].depends_on:
            if dep in by_name:
                visit(dep)
        in_progress.discard(name)

        visited.add(name)
        ordered.append(by_name[name])

    for stage in stages:
        visit(stage.name)

    return ordered


def reachable_from(stages: list[StageDef], start_from: str) -> set[str]:
    """Every stage that *is* `start_from` or transitively depends on it --
    i.e. the sub-DAG a run should execute when told to start partway
    through instead of at the natural roots. Assumes `stages` is acyclic
    (call `topological_order` first, which validates that)."""
    by_name = {s.name: s for s in stages}
    if start_from not in by_name:
        raise UnknownDependencyError(f"unknown start_from stage {start_from!r}")

    memo: dict[str, bool] = {}

    def depends_on_start(name: str) -> bool:
        if name not in memo:
            memo[name] = name == start_from or any(
                depends_on_start(dep) for dep in by_name[name].depends_on if dep in by_name
            )
        return memo[name]

    return {name for name in by_name if depends_on_start(name)}
