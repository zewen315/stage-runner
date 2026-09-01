"""Background worker: the only thing that consumes run requests off the
queue and actually executes a workflow. Nothing user-facing calls this
directly -- the Workflow Service enqueues, this dequeues.

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

from runner import Runner
from scheduler import Scheduler
from workflow_loader import load_workflow

QUEUE_KEY = "stagerunner:runs"

Report = Callable[[str, int, str, dict], None]


def process_message(
    message: dict,
    *,
    workflows_root: Path,
    output_root: Path,
    resources: ResourceClient,
    report: Report,
) -> None:
    run_id = message["run_id"]
    workflow_name = message["workflow_name"]

    report(workflow_name, run_id, "start", {})

    try:
        workflow_dir = workflows_root / workflow_name
        output_dir = output_root / workflow_name
        registry = load_workflow(workflow_dir)
        runner = Runner(resources, workflow_dir=workflow_dir, output_dir=output_dir)
        result = Scheduler(registry, runner).run()
    except Exception as exc:  # noqa: BLE001 -- report and move on, don't crash the worker
        report(workflow_name, run_id, "fail", {"error": str(exc)})
        return

    if result.failed:
        report(workflow_name, run_id, "fail", {"error": f"{result.failed}: {result.error}"})
    else:
        report(workflow_name, run_id, "complete", {})


def _http_report(workflow_service_url: str) -> Report:
    def report(workflow_name: str, run_id: int, action: str, body: dict) -> None:
        response = httpx.post(
            f"{workflow_service_url}/workflows/{workflow_name}/runs/{run_id}/{action}",
            json=body,
            timeout=10,
        )
        response.raise_for_status()

    return report


def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    workflows_root = Path(os.environ.get("WORKFLOWS_ROOT", "/workflows"))
    output_root = Path(os.environ.get("OUTPUT_ROOT", "/output"))
    resource_store_url = os.environ.get("RESOURCE_STORE_URL", "http://localhost:8000")
    workflow_service_url = os.environ.get("WORKFLOW_SERVICE_URL", "http://localhost:8001")

    resources = HttpResourceClient(resource_store_url)
    report = _http_report(workflow_service_url)

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
                output_root=output_root,
                resources=resources,
                report=report,
            )
        except Exception as exc:  # noqa: BLE001 -- one bad message shouldn't kill the worker
            print(f"error processing {message}: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
