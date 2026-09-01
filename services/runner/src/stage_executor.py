"""StageExecutor: runs a stage's pure function -- and only that function
call, not the resource_store I/O around it (see `runner.py`).

`InProcessStageExecutor` is the default -- every existing test, and any
local/non-Docker use, gets exactly today's behavior: the already-loaded
`stage_def.fn` is just called directly.

`DockerStageExecutor` is the real isolation: spawns a fresh, single-use,
network-disabled container per call -- the Runner's own image, running
`execute_stage.py` instead of `worker.py` -- with the resolved input
*values* passed in as JSON. The spawned container never touches
resource_store or the network at all; it re-loads the workflow from
scratch (via `workflow_name`/`stage_name`) since a live Python function
object can't be shipped across a process boundary.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from stages import StageDef


class StageExecutor(Protocol):
    def run(self, stage_def: StageDef, inputs: dict[str, Any], *, workflow_name: str | None) -> Any:
        """Runs stage_def's function with the resolved input values,
        returns its result. Raises on failure."""
        ...


class InProcessStageExecutor:
    def run(self, stage_def: StageDef, inputs: dict[str, Any], *, workflow_name: str | None) -> Any:
        return stage_def.fn(**inputs)


class DockerStageExecutor:
    def __init__(self, image: str, workflows_host_path: str, workflows_root: str = "/workflows"):
        import docker

        self._client = docker.from_env()
        self._image = image
        self._workflows_host_path = workflows_host_path
        self._workflows_root = workflows_root

    def run(self, stage_def: StageDef, inputs: dict[str, Any], *, workflow_name: str | None) -> Any:
        import docker.errors

        environment = {
            "WORKFLOW_NAME": workflow_name,
            "STAGE_NAME": stage_def.name,
            "STAGE_INPUTS_JSON": json.dumps(inputs),
            "WORKFLOWS_ROOT": self._workflows_root,
        }
        volumes = {self._workflows_host_path: {"bind": self._workflows_root, "mode": "ro"}}

        try:
            output = self._client.containers.run(
                self._image,
                command=["uv", "run", "--no-dev", "python", "src/execute_stage.py"],
                environment=environment,
                volumes=volumes,
                network_disabled=True,
                remove=True,
            )
        except docker.errors.ContainerError as exc:
            raise RuntimeError(self._parse_result(exc.stderr or b"").get("error", str(exc))) from exc

        result = self._parse_result(output)
        if not result.get("ok", False):
            raise RuntimeError(result.get("error", "execute_stage.py failed with no error message"))
        return result["result"]

    @staticmethod
    def _parse_result(output: bytes) -> dict:
        try:
            last_line = output.decode().strip().splitlines()[-1]
            return json.loads(last_line)
        except (IndexError, ValueError):
            return {"ok": False, "error": f"could not parse execute_stage.py output: {output!r}"}
