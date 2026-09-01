"""Executes exactly one stage: resolves its inputs, does the work, writes
the result back. The Runner is the only thing that touches the Resource
Store -- it has no DAG knowledge at all. Dependency-aware ordering lives
in the Scheduler service now, one process boundary away, dispatching one
stage at a time; the Runner just executes whatever single stage it's
handed.

The actual function call goes through a `StageExecutor` (stage_executor.py),
not a direct call, so it can be isolated into a container without this
module needing to know or care.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resource_store_client import ResourceClient
from stage_executor import InProcessStageExecutor, StageExecutor
from stages import StageDef


class Runner:
    def __init__(
        self,
        resources: ResourceClient,
        workflow_dir: Path | None = None,
        executor: StageExecutor | None = None,
    ):
        self._resources = resources
        self._workflow_dir = workflow_dir
        self._executor = executor or InProcessStageExecutor()

    def run_stage(
        self,
        stage_def: StageDef,
        input_versions: dict[str, int],
        promote: bool,
        is_test: bool = False,
    ) -> int:
        """Runs one stage. `input_versions` pins specific dependencies to a
        given version instead of "current" -- a fully-resolved map for an
        orchestrated stage (the Scheduler pins every dependency to this
        run's own upstream outputs), a partial or empty one for a
        standalone StageRun (unpinned dependencies fall back to current).
        A stage with no dependencies (a workflow's root) expects its own
        resource to already exist -- see `resource upload` in the CLI.
        Returns the produced resource's version."""
        inputs = {}
        dep_versions: list[tuple[str, int]] = []
        for dep in stage_def.depends_on:
            version, value = self._resolve_input(dep, input_versions)
            inputs[dep] = value
            dep_versions.append((dep, version))

        workflow_name = self._workflow_dir.name if self._workflow_dir else None
        result = self._executor.run(stage_def, inputs, workflow_name=workflow_name)

        version = self._resources.upload_version(stage_def.name, result, is_test=is_test)
        self._resources.update_dependencies(stage_def.name, version, dep_versions)
        if promote:
            self._resources.promote(stage_def.name, version)
        return version

    def _resolve_input(self, dep: str, input_versions: dict[str, int]) -> tuple[int, Any]:
        if dep in input_versions:
            version = input_versions[dep]
            return version, self._resources.get_version(dep, version)
        return self._resources.get(dep)
