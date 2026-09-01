from __future__ import annotations

from dataclasses import replace

from models import Run, RunStatus


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[int, Run] = {}
        self._next_id = 1

    def create(self, workflow_name: str, requested_at: str) -> Run:
        run = Run(
            id=self._next_id,
            workflow_name=workflow_name,
            status=RunStatus.REQUESTED,
            requested_at=requested_at,
            started_at=None,
            finished_at=None,
            error=None,
        )
        self._runs[run.id] = run
        self._next_id += 1
        return run

    def get(self, workflow_name: str, run_id: int) -> Run | None:
        run = self._runs.get(run_id)
        if run is None or run.workflow_name != workflow_name:
            return None
        return run

    def mark_running(self, run_id: int, started_at: str) -> None:
        self._runs[run_id] = replace(self._runs[run_id], status=RunStatus.RUNNING, started_at=started_at)

    def mark_completed(self, run_id: int, finished_at: str) -> None:
        self._runs[run_id] = replace(
            self._runs[run_id], status=RunStatus.COMPLETED, finished_at=finished_at
        )

    def mark_failed(self, run_id: int, finished_at: str, error: str) -> None:
        self._runs[run_id] = replace(
            self._runs[run_id], status=RunStatus.FAILED, finished_at=finished_at, error=error
        )


class InMemoryRunQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[int, str]] = []

    def enqueue(self, run_id: int, workflow_name: str) -> None:
        self.enqueued.append((run_id, workflow_name))
