"""Executes exactly one stage: resolves its inputs, does the work, writes
results back. The Runner is the only thing that touches the Resource Store
-- it has no DAG knowledge at all. Dependency-aware ordering lives in the
Scheduler service now, one process boundary away, dispatching one stage at
a time; the Runner just executes whatever single stage it's handed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resource_store_client import ResourceClient
from stages import StageDef


class Runner:
    def __init__(
        self,
        resources: ResourceClient,
        workflow_dir: Path | None = None,
        output_dir: Path | None = None,
    ):
        self._resources = resources
        self._workflow_dir = workflow_dir
        # Import paths resolve against workflow_dir -- checked-in content,
        # legitimately read-only. Export paths resolve against a *separate*
        # output_dir -- a run artifact, never inside the workflow's own
        # (read-only-mounted, in production) directory. Falls back to
        # workflow_dir only for convenience when nothing else is given
        # (e.g. quick local/manual testing).
        self._output_dir = output_dir if output_dir is not None else workflow_dir

    def run_stage(
        self,
        stage_def: StageDef,
        input_versions: dict[str, int],
        promote: bool,
        is_test: bool = False,
    ) -> int | None:
        """Runs one stage. `input_versions` pins specific dependencies to a
        given version instead of "current" -- a fully-resolved map for an
        orchestrated stage (the Scheduler pins every dependency to this
        run's own upstream outputs), a partial or empty one for a
        standalone StageRun (unpinned dependencies fall back to current).
        Returns the produced resource's version, or None for an export
        stage (which produces no resource)."""
        if stage_def.kind == "import":
            return self._run_import(stage_def, promote, is_test)
        if stage_def.kind == "export":
            self._run_export(stage_def, input_versions)
            return None
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
        self._resources.create_resource_if_missing(stage_def.name)
        version = self._resources.upload_version(stage_def.name, value, is_test=is_test)
        if promote:
            self._resources.promote(stage_def.name, version)
        return version

    def _run_export(self, stage_def: StageDef, input_versions: dict[str, int]) -> None:
        [dep] = stage_def.depends_on
        _, value = self._resolve_input(dep, input_versions)
        output_path = self._resolve(stage_def.path, self._output_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(value))

    def _run_stage_fn(
        self, stage_def: StageDef, input_versions: dict[str, int], promote: bool, is_test: bool
    ) -> int:
        inputs = {}
        dep_versions: list[tuple[str, int]] = []
        for dep in stage_def.depends_on:
            version, value = self._resolve_input(dep, input_versions)
            inputs[dep] = value
            dep_versions.append((dep, version))

        result = stage_def.fn(**inputs)

        self._resources.create_resource_if_missing(stage_def.name)
        version = self._resources.upload_version(stage_def.name, result, is_test=is_test)
        self._resources.update_dependencies(stage_def.name, version, dep_versions)
        if promote:
            self._resources.promote(stage_def.name, version)
        return version
