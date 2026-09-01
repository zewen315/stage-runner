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

from models import Schedule, ScheduleScope, StageRun, WorkflowRun


class ScheduleRepository(Protocol):
    def create(
        self,
        workflow_name: str,
        scope: ScheduleScope,
        stage_name: str | None,
        input_versions: dict[str, int] | None,
        promote: bool | None,
        requested_at: str,
    ) -> Schedule: ...

    def get(self, workflow_name: str, schedule_id: int) -> Schedule | None: ...


class WorkflowRunRepository(Protocol):
    def get(self, workflow_name: str, run_id: int) -> WorkflowRun | None: ...


class StageRunRepository(Protocol):
    def get(self, workflow_name: str, stage_run_id: int) -> StageRun | None: ...

    def list_for_workflow_run(self, run_id: int) -> list[StageRun]: ...

    def mark_running(self, stage_run_id: int, started_at: str) -> None: ...

    def mark_completed(self, stage_run_id: int, finished_at: str, output_version: int | None) -> None: ...

    def mark_failed(self, stage_run_id: int, finished_at: str, error: str) -> None: ...
