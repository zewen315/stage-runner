"""Storage interfaces the service depends on -- same reasoning as
resource_store's ports.py: depending on Protocols instead of concrete
clients keeps WorkflowService testable with fast in-memory fakes, with the
real Postgres adapters swapped in only when actually running.

Notably thin on writes: workflow_service only ever *creates* `schedules`
rows (client requests) and *updates* `stage_runs` status (worker
callbacks). It never creates or updates a `runs`/`stage_runs` row's
lifecycle beyond that -- the Scheduler is the sole creator of both, and the
sole thing that ever changes a WorkflowRun's status, writing Postgres
directly rather than through this service.
"""

from __future__ import annotations

from typing import Protocol

from models import RecurringSchedule, Schedule, StageRun, WorkflowRun


class ScheduleRepository(Protocol):
    def create(
        self,
        workflow_name: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool | None,
        requested_at: str,
        run_at: str | None = None,
        on_failure: str | None = None,
    ) -> Schedule: ...

    def get(self, workflow_name: str, schedule_id: int) -> Schedule | None: ...

    def list_pending(self, workflow_name: str) -> list[Schedule]:
        """Schedules not yet dispatched (dispatched_at is None), most
        recent first. Once dispatched, a schedule's info is superseded by
        the WorkflowRun it created -- not returned here."""
        ...


class RecurringScheduleRepository(Protocol):
    def create(
        self,
        workflow_name: str,
        cron_expression: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool | None,
        next_run_at: str,
        created_at: str,
        on_failure: str | None = None,
    ) -> RecurringSchedule: ...

    def get(self, workflow_name: str, recurring_schedule_id: int) -> RecurringSchedule | None: ...

    def list_for_workflow(self, workflow_name: str) -> list[RecurringSchedule]: ...

    def set_enabled(self, recurring_schedule_id: int, enabled: bool) -> None: ...


class WorkflowRunRepository(Protocol):
    def get(self, workflow_name: str, run_id: int) -> WorkflowRun | None: ...

    def list_for_workflow(self, workflow_name: str, limit: int) -> list[WorkflowRun]:
        """Most-recent-first."""
        ...

    def mark_cancel_requested(self, run_id: int) -> None:
        """Records intent only -- the Scheduler is still the one that
        actually changes `status`, on its next tick, the same hand-off
        `run_at` already uses."""
        ...


class StageRunRepository(Protocol):
    def get(self, workflow_name: str, stage_run_id: int) -> StageRun | None: ...

    def list_for_workflow_run(self, run_id: int) -> list[StageRun]: ...

    def mark_running(self, stage_run_id: int, started_at: str) -> None: ...

    def mark_completed(
        self, stage_run_id: int, finished_at: str, output_version: int | None, attempts: int = 1
    ) -> None: ...

    def mark_failed(
        self, stage_run_id: int, finished_at: str, error: str, attempts: int = 1
    ) -> None: ...
