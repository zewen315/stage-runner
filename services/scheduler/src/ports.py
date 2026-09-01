"""Storage/queue interfaces the poller depends on -- same reasoning as
workflow_service's ports.py: depending on Protocols instead of concrete
clients keeps `poll_once` testable with fast in-memory fakes, with the
real Postgres/Redis adapters swapped in only when actually running.

The Scheduler is the sole creator of `runs`/`stage_runs` rows and the only
thing that ever changes a WorkflowRun's status -- workflow_service only
ever creates `schedules` rows and updates a StageRun's status via worker
callbacks.
"""

from __future__ import annotations

from typing import Protocol

from models import ActiveWorkflowRun, PendingSchedule, StageRunRecord


class ScheduleStore(Protocol):
    def pending_schedules(self) -> list[PendingSchedule]: ...

    def mark_schedule_dispatched(
        self, schedule_id: int, *, run_id: int | None = None, stage_run_id: int | None = None
    ) -> None: ...

    def create_workflow_run(self, workflow_name: str) -> int: ...

    def create_stage_run(
        self,
        workflow_run_id: int | None,
        workflow_name: str,
        stage_name: str,
        input_versions: dict[str, int],
        promote: bool,
    ) -> int: ...

    def active_workflow_runs(self) -> list[ActiveWorkflowRun]: ...

    def stage_runs_for_workflow_run(self, run_id: int) -> list[StageRunRecord]: ...

    def mark_workflow_run_running(self, run_id: int) -> None: ...

    def mark_workflow_run_completed(self, run_id: int) -> None: ...

    def mark_workflow_run_failed(self, run_id: int, error: str) -> None: ...


class RunQueue(Protocol):
    def enqueue_stage_run(
        self,
        stage_run_id: int,
        workflow_run_id: int | None,
        workflow_name: str,
        stage_name: str,
        input_versions: dict[str, int],
        promote: bool,
    ) -> None: ...
