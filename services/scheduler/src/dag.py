"""Topological ordering of a StageRegistry's stages, by `depends_on`."""

from __future__ import annotations

from stages import StageDef


class CycleError(Exception):
    """Raised when the stage graph has a dependency cycle."""


class UnknownDependencyError(Exception):
    """Raised when a stage depends on a name that isn't registered."""


def topological_order(stages: list[StageDef]) -> list[StageDef]:
    by_name = {s.name: s for s in stages}

    for stage in stages:
        for dep in stage.depends_on:
            if dep not in by_name:
                raise UnknownDependencyError(f"{stage.name!r} depends on unregistered stage {dep!r}")

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
            visit(dep)
        in_progress.discard(name)

        visited.add(name)
        ordered.append(by_name[name])

    for stage in stages:
        visit(stage.name)

    return ordered
