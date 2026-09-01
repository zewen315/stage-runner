"""Domain logic: the control plane for workflow definitions and trigger
requests. Accepting a run/stage-run request means creating a `schedules`
row -- nothing here ever creates a `runs`/`stage_runs` row or touches a
queue. The Scheduler (a separate, internal service) polls `schedules`
directly in Postgres, dispatches due work, and owns `runs`/`stage_runs`
end to end; the Runner worker executes exactly one stage per dispatch and
calls back into `start_stage_run`/`complete_stage_run`/`fail_stage_run` as
it makes progress. This service never calls the Scheduler or the Runner,
only the other way around.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from errors import (
    RunNotFoundError,
    ScheduleNotFoundError,
    StageRunNotFoundError,
    WorkflowNotFoundError,
)
from models import RunStatus, Schedule, ScheduleScope, ScheduleStatus, StageRun, WorkflowRun
from ports import ScheduleRepository, StageRunRepository, WorkflowRunRepository


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowService:
    def __init__(
        self,
        schedules: ScheduleRepository,
        workflow_runs: WorkflowRunRepository,
        stage_runs: StageRunRepository,
        workflows_root: Path,
    ):
        self._schedules = schedules
        self._workflow_runs = workflow_runs
        self._stage_runs = stage_runs
        self._workflows_root = workflows_root

    def _require_workflow(self, name: str) -> None:
        if not (self._workflows_root / name).is_dir():
            raise WorkflowNotFoundError(f"no workflow {name!r} under {self._workflows_root}")

    def _require_schedule(self, workflow_name: str, schedule_id: int) -> Schedule:
        schedule = self._schedules.get(workflow_name, schedule_id)
        if schedule is None:
            raise ScheduleNotFoundError(f"no schedule {schedule_id} for workflow {workflow_name!r}")
        return schedule

    def _require_run(self, workflow_name: str, run_id: int) -> WorkflowRun:
        run = self._workflow_runs.get(workflow_name, run_id)
        if run is None:
            raise RunNotFoundError(f"no run {run_id} for workflow {workflow_name!r}")
        return run

    def _require_stage_run(self, workflow_name: str, stage_run_id: int) -> StageRun:
        stage_run = self._stage_runs.get(workflow_name, stage_run_id)
        if stage_run is None:
            raise StageRunNotFoundError(f"no stage run {stage_run_id} for workflow {workflow_name!r}")
        return stage_run

    def request_run(self, workflow_name: str) -> Schedule:
        """Client-facing: trigger a whole workflow, once. Record intent,
        return immediately -- the Scheduler picks up undispatched schedules
        on its own poll cycle and drives the whole DAG from there."""
        self._require_workflow(workflow_name)
        return self._schedules.create(
            workflow_name,
            ScheduleScope.WORKFLOW,
            stage_name=None,
            input_versions=None,
            promote=None,
            requested_at=_utcnow(),
        )

    def request_stage_run(
        self,
        workflow_name: str,
        stage_name: str,
        input_versions: dict[str, int] | None = None,
        promote: bool = False,
    ) -> Schedule:
        """Client-facing: trigger a single stage standalone, once -- e.g.
        testing a stage against a pinned historical input. Stage-name
        existence isn't validated here (this service never imports
        workflow code); an unknown stage fails at dispatch/execution time
        instead."""
        self._require_workflow(workflow_name)
        return self._schedules.create(
            workflow_name,
            ScheduleScope.STAGE,
            stage_name=stage_name,
            input_versions=input_versions or {},
            promote=promote,
            requested_at=_utcnow(),
        )

    def get_schedule_status(self, workflow_name: str, schedule_id: int) -> ScheduleStatus:
        """Client-facing polling target: proxies the status of whatever
        this schedule dispatched to, regardless of scope, so callers only
        ever need to poll one endpoint."""
        schedule = self._require_schedule(workflow_name, schedule_id)

        if schedule.dispatched_at is None:
            return ScheduleStatus(
                id=schedule.id,
                workflow_name=schedule.workflow_name,
                scope=schedule.scope,
                stage_name=schedule.stage_name,
                status=RunStatus.REQUESTED.value,
                error=None,
                run_id=None,
                stage_run_id=None,
            )

        if schedule.scope == ScheduleScope.WORKFLOW:
            run = self._require_run(workflow_name, schedule.run_id)
            return ScheduleStatus(
                id=schedule.id,
                workflow_name=schedule.workflow_name,
                scope=schedule.scope,
                stage_name=schedule.stage_name,
                status=run.status.value,
                error=run.error,
                run_id=run.id,
                stage_run_id=None,
            )

        stage_run = self._require_stage_run(workflow_name, schedule.stage_run_id)
        return ScheduleStatus(
            id=schedule.id,
            workflow_name=schedule.workflow_name,
            scope=schedule.scope,
            stage_name=schedule.stage_name,
            status=stage_run.status.value,
            error=stage_run.error,
            run_id=None,
            stage_run_id=stage_run.id,
        )

    def get_run(self, workflow_name: str, run_id: int) -> WorkflowRun:
        return self._require_run(workflow_name, run_id)

    def list_stage_runs_for_run(self, workflow_name: str, run_id: int) -> list[StageRun]:
        self._require_run(workflow_name, run_id)
        return self._stage_runs.list_for_workflow_run(run_id)

    def get_stage_run(self, workflow_name: str, stage_run_id: int) -> StageRun:
        return self._require_stage_run(workflow_name, stage_run_id)

    def start_stage_run(self, workflow_name: str, stage_run_id: int) -> None:
        """Worker-facing: called by the Runner when it picks up a stage run."""
        self._require_stage_run(workflow_name, stage_run_id)
        self._stage_runs.mark_running(stage_run_id, started_at=_utcnow())

    def complete_stage_run(self, workflow_name: str, stage_run_id: int, output_version: int | None) -> None:
        """Worker-facing."""
        self._require_stage_run(workflow_name, stage_run_id)
        self._stage_runs.mark_completed(stage_run_id, finished_at=_utcnow(), output_version=output_version)

    def fail_stage_run(self, workflow_name: str, stage_run_id: int, error: str) -> None:
        """Worker-facing."""
        self._require_stage_run(workflow_name, stage_run_id)
        self._stage_runs.mark_failed(stage_run_id, finished_at=_utcnow(), error=error)
