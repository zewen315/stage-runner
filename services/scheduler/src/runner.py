"""Executes exactly one stage: resolves its inputs, does the work, writes
results back. Deliberately separate from Scheduler -- Scheduler decides
*what* runs next (DAG order), Runner is the only thing that touches the
Resource Store. Mirrors how Airflow separates its Scheduler from Workers;
here it's an internal module boundary for now (nothing needs the isolation
of a separate process/container yet), but it's the seam that split would
grow from later.
"""

from __future__ import annotations

import json
from pathlib import Path

from resource_store_client import ResourceClient
from stages import StageDef


class Runner:
    def __init__(self, resources: ResourceClient, workflow_dir: Path | None = None):
        self._resources = resources
        self._workflow_dir = workflow_dir

    def run(self, stage_def: StageDef) -> None:
        if stage_def.kind == "import":
            self._run_import(stage_def)
        elif stage_def.kind == "export":
            self._run_export(stage_def)
        else:
            self._run_stage_fn(stage_def)

    def _resolve(self, path: str) -> Path:
        """Relative import/export paths are resolved against the workflow
        file's own directory, not the process's cwd -- otherwise a workflow
        only works when run from one specific directory."""
        resolved = Path(path)
        if not resolved.is_absolute() and self._workflow_dir is not None:
            resolved = self._workflow_dir / resolved
        return resolved

    def _run_import(self, stage_def: StageDef) -> None:
        value = json.loads(self._resolve(stage_def.path).read_text())
        self._resources.create_resource_if_missing(stage_def.name)
        version = self._resources.upload_version(stage_def.name, value)
        self._resources.promote(stage_def.name, version)

    def _run_export(self, stage_def: StageDef) -> None:
        [dep] = stage_def.depends_on
        _, value = self._resources.get(dep)
        output_path = self._resolve(stage_def.path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(value))

    def _run_stage_fn(self, stage_def: StageDef) -> None:
        inputs = {}
        dep_versions: list[tuple[str, int]] = []
        for dep in stage_def.depends_on:
            version, value = self._resources.get(dep)
            inputs[dep] = value
            dep_versions.append((dep, version))

        result = stage_def.fn(**inputs)

        self._resources.create_resource_if_missing(stage_def.name)
        version = self._resources.upload_version(stage_def.name, result)
        self._resources.update_dependencies(stage_def.name, version, dep_versions)
        self._resources.promote(stage_def.name, version)
