"""Executes exactly one stage: resolves its inputs, does the work, writes
results back. The Runner is the only thing that touches the Resource Store
-- it has no DAG knowledge at all. Dependency-aware ordering lives in the
Scheduler service now, one process boundary away, dispatching one stage at
a time; the Runner just executes whatever single stage it's handed.

The actual function call for a "stage"-kind StageDef -- the only kind that
runs arbitrary, user-authored code -- goes through a `StageExecutor`
(stage_executor.py), not a direct call, so it can be isolated into a
container without this module needing to know or care.
"""

from __future__ import annotations

import json
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
        Returns the produced resource's version -- every stage, including
        a workflow's last one, produces a resource."""
        if stage_def.kind == "import":
            return self._run_import(stage_def, promote, is_test)
        return self._run_stage_fn(stage_def, input_versions, promote, is_test)

    @staticmethod
    def _resolve(path: str, base: Path | None) -> Path:
        resolved = Path(path)
        if not resolved.is_absolute() and base is not None:
            resolved = base / resolved
        return resolved

    def _resolve_input(self, dep: str, input_versions: dict[str, int]) -> tuple[int, Any]:
        if dep in input_versions:
            version = input_versions[dep]
            return version, self._resources.get_version(dep, version)
        return self._resources.get(dep)

    def _run_import(self, stage_def: StageDef, promote: bool, is_test: bool) -> int:
        input_path = self._resolve(stage_def.path, self._workflow_dir)
        value = json.loads(input_path.read_text())
        version = self._resources.upload_version(stage_def.name, value, is_test=is_test)
        if promote:
            self._resources.promote(stage_def.name, version)
        return version

    def _run_stage_fn(
        self, stage_def: StageDef, input_versions: dict[str, int], promote: bool, is_test: bool
    ) -> int:
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
