"""Domain logic: the control plane for workflow runs. Accepting a run
request means creating a `requested` record and enqueueing it -- nothing
here executes a workflow. The Scheduler (a separate, internal worker
process) consumes the queue and calls back into `start_run`/`complete_run`/
`fail_run` as it makes progress; this service never calls the Scheduler,
only the other way around.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from errors import RunNotFoundError, WorkflowNotFoundError
from models import Run
from ports import RunQueue, RunRepository


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowService:
    def __init__(self, runs: RunRepository, queue: RunQueue, workflows_root: Path):
        self._runs = runs
        self._queue = queue
        self._workflows_root = workflows_root

    def _require_workflow(self, name: str) -> None:
        if not (self._workflows_root / name).is_dir():
            raise WorkflowNotFoundError(f"no workflow {name!r} under {self._workflows_root}")

    def _require_run(self, workflow_name: str, run_id: int) -> Run:
        run = self._runs.get(workflow_name, run_id)
        if run is None:
            raise RunNotFoundError(f"no run {run_id} for workflow {workflow_name!r}")
        return run

    def request_run(self, workflow_name: str) -> Run:
        """Client-facing: record intent, enqueue, return immediately. Does
        not execute anything."""
        self._require_workflow(workflow_name)
        run = self._runs.create(workflow_name, requested_at=_utcnow())
        self._queue.enqueue(run.id, workflow_name)
        return run

    def get_run(self, workflow_name: str, run_id: int) -> Run:
        return self._require_run(workflow_name, run_id)

    def start_run(self, workflow_name: str, run_id: int) -> None:
        """Worker-facing: called by the Scheduler when it picks up a run."""
        self._require_run(workflow_name, run_id)
        self._runs.mark_running(run_id, started_at=_utcnow())

    def complete_run(self, workflow_name: str, run_id: int) -> None:
        """Worker-facing."""
        self._require_run(workflow_name, run_id)
        self._runs.mark_completed(run_id, finished_at=_utcnow())

    def fail_run(self, workflow_name: str, run_id: int, error: str) -> None:
        """Worker-facing."""
        self._require_run(workflow_name, run_id)
        self._runs.mark_failed(run_id, finished_at=_utcnow(), error=error)
