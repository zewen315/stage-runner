"""Background worker: the only thing that consumes stage-run dispatches
off the queue and actually executes a stage. Nothing user-facing calls
this directly -- the Scheduler service is the sole thing that pushes onto
the queue, one stage at a time; the worker has no DAG knowledge, it just
executes exactly the one stage it's handed.

`process_message` takes its collaborators (a ResourceClient, a report
callback) as parameters rather than constructing them itself, so it's
testable with the same in-memory fakes used elsewhere in this project --
no real Redis, Resource Store, or Workflow Service needed for
tests/test_worker.py. `main` is the thin, untested wiring that builds the
real HTTP-based versions and runs the blocking consume loop.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

import httpx
import redis
from resource_store_client import HttpResourceClient, ResourceClient
from stage_executor import StageExecutor
from workflow_loader import load_workflow

from runner import Runner

QUEUE_KEY = "stagerunner:stage_runs"

Report = Callable[[str, int, str, dict], None]


def process_message(
    message: dict,
    *,
    workflows_root: Path,
    resources: ResourceClient,
    report: Report,
    executor: StageExecutor | None = None,
) -> None:
    stage_run_id = message["stage_run_id"]
    workflow_name = message["workflow_name"]
    stage_name = message["stage_name"]
    input_versions = message["input_versions"]
    promote = message["promote"]
    is_test = not promote

    report(workflow_name, stage_run_id, "start", {})

    try:
        workflow_dir = workflows_root / workflow_name
        registry = load_workflow(workflow_dir)
        stage_def = registry.get(stage_name)
        runner = Runner(resources, workflow_dir=workflow_dir, executor=executor)
        output_version = runner.run_stage(stage_def, input_versions, promote, is_test=is_test)
    except Exception as exc:  # noqa: BLE001 -- report and move on, don't crash the worker
        report(workflow_name, stage_run_id, "fail", {"error": str(exc)})
        return

    report(workflow_name, stage_run_id, "complete", {"output_version": output_version})


def _http_report(workflow_service_url: str) -> Report:
    def report(workflow_name: str, stage_run_id: int, action: str, body: dict) -> None:
        response = httpx.post(
            f"{workflow_service_url}/workflows/{workflow_name}/stage-runs/{stage_run_id}/{action}",
            json=body,
            timeout=10,
        )
        response.raise_for_status()

    return report


def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    workflows_root = Path(os.environ.get("WORKFLOWS_ROOT", "/workflows"))
    resource_store_url = os.environ.get("RESOURCE_STORE_URL", "http://localhost:8000")
    workflow_service_url = os.environ.get("WORKFLOW_SERVICE_URL", "http://localhost:8001")
    stage_executor_image = os.environ.get("STAGE_EXECUTOR_IMAGE")
    workflows_host_path = os.environ.get("WORKFLOWS_HOST_PATH")

    resources = HttpResourceClient(resource_store_url)
    report = _http_report(workflow_service_url)

    executor: StageExecutor | None = None
    if stage_executor_image and workflows_host_path:
        from stage_executor import DockerStageExecutor

        executor = DockerStageExecutor(
            image=stage_executor_image,
            workflows_host_path=workflows_host_path,
            workflows_root=str(workflows_root),
        )
        print(f"stage execution: containerized (image={stage_executor_image})", flush=True)
    else:
        print("stage execution: in-process (STAGE_EXECUTOR_IMAGE/WORKFLOWS_HOST_PATH not set)", flush=True)

    client = redis.from_url(redis_url)
    print(f"worker listening on {QUEUE_KEY}...", flush=True)

    while True:
        try:
            popped = client.brpop(QUEUE_KEY, timeout=0)
        except redis.exceptions.TimeoutError:
            # BRPOP(timeout=0) means "block forever" server-side, but the
            # client's own socket read can still time out while nothing is
            # queued -- that's not a real failure, just an empty queue.
            continue
        except redis.exceptions.ConnectionError as exc:
            print(f"redis connection error, retrying: {exc}", file=sys.stderr, flush=True)
            time.sleep(1)
            continue

        if popped is None:
            continue

        _, raw = popped
        message = json.loads(raw)
        print(f"processing {message}", flush=True)
        try:
            process_message(
                message,
                workflows_root=workflows_root,
                resources=resources,
                report=report,
                executor=executor,
            )
        except Exception as exc:  # noqa: BLE001 -- one bad message shouldn't kill the worker
            print(f"error processing {message}: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
