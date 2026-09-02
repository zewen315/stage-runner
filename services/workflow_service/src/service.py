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

from dag import topological_order
from workflow_loader import load_workflow

from errors import (
    RunNotFoundError,
    ScheduleNotFoundError,
    StageRunNotFoundError,
    WorkflowNotFoundError,
)
from models import RunStatus, Schedule, ScheduleStatus, StageInfo, StageRun, WorkflowRun
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

    def request_run(
        self,
        workflow_name: str,
        start_from: str | None = None,
        stop_after: str | None = None,
        input_versions: dict[str, int] | None = None,
        promote: bool | None = None,
        run_at: str | None = None,
    ) -> Schedule:
        """Client-facing: trigger a run, once. `start_from`/`stop_after`
        (both optional) narrow it to a sub-range of the workflow's DAG --
        unset both for a full run from the natural roots to completion;
        set both to the same stage name to run just that one stage.
        `input_versions` supplies whichever of `start_from`'s dependencies
        won't be produced within this run (only meaningful when
        `start_from` is set). `promote` left unset lets the Scheduler
        apply its default (true only for a full run). `run_at` left unset
        means eligible for dispatch as soon as the Scheduler sees it
        (today's only behavior); set it to delay dispatch until then --
        the Scheduler is the one that actually enforces this, on its own
        pending_schedules() query, not anything here. Stage-name existence
        isn't validated here -- an unknown name fails at dispatch time
        instead, same as always; see `list_stages` below for the one place
        this service does load a workflow's registry, for a different
        reason (offering real names to pick from, not validating one).
        Record intent, return immediately -- the Scheduler picks up
        undispatched schedules on its own poll cycle."""
        self._require_workflow(workflow_name)
        return self._schedules.create(
            workflow_name,
            start_from,
            stop_after,
            input_versions,
            promote,
            requested_at=_utcnow(),
            run_at=run_at,
        )

    def get_schedule_status(self, workflow_name: str, schedule_id: int) -> ScheduleStatus:
        """Client-facing polling target: proxies the status of the
        WorkflowRun this schedule dispatched to, once it has."""
        schedule = self._require_schedule(workflow_name, schedule_id)

        if schedule.dispatched_at is None:
            return ScheduleStatus(
                id=schedule.id,
                workflow_name=schedule.workflow_name,
                start_from=schedule.start_from,
                stop_after=schedule.stop_after,
                run_at=schedule.run_at,
                status=RunStatus.REQUESTED.value,
                error=None,
                run_id=None,
            )

        run = self._require_run(workflow_name, schedule.run_id)
        return ScheduleStatus(
            id=schedule.id,
            workflow_name=schedule.workflow_name,
            start_from=schedule.start_from,
            stop_after=schedule.stop_after,
            run_at=schedule.run_at,
            status=run.status.value,
            error=run.error,
            run_id=run.id,
        )

    def list_pending_schedules(self, workflow_name: str) -> list[ScheduleStatus]:
        """Every pending schedule is trivially "requested" (dispatched_at
        is None is exactly what `list_pending` filters on) -- build the
        status directly instead of a redundant get_schedule_status() per
        row."""
        self._require_workflow(workflow_name)
        return [
            ScheduleStatus(
                id=s.id,
                workflow_name=s.workflow_name,
                start_from=s.start_from,
                stop_after=s.stop_after,
                run_at=s.run_at,
                status=RunStatus.REQUESTED.value,
                error=None,
                run_id=None,
            )
            for s in self._schedules.list_pending(workflow_name)
        ]

    def list_stages(self, workflow_name: str) -> list[StageInfo]:
        """Ordered stage names plus each one's direct dependencies -- lets
        a client (the web UI's "start from" dropdown) offer real names to
        pick from and know which upstream versions it needs to supply as
        input_versions when skipping ahead to one. This does load the
        workflow's actual registry (a plain, side-effect-free Python
        import -- the same thing the Scheduler already does to run it),
        unlike every other method here."""
        self._require_workflow(workflow_name)
        registry = load_workflow(self._workflows_root / workflow_name)
        return [
            StageInfo(name=stage.name, depends_on=list(stage.depends_on))
            for stage in topological_order(registry.all())
        ]

    def list_workflows(self) -> list[str]:
        return sorted(
            d.name
            for d in self._workflows_root.iterdir()
            if d.is_dir() and not d.name.startswith(("_", "."))
        )

    def get_run(self, workflow_name: str, run_id: int) -> WorkflowRun:
        return self._require_run(workflow_name, run_id)

    def list_runs(self, workflow_name: str, limit: int = 50) -> list[WorkflowRun]:
        self._require_workflow(workflow_name)
        return self._workflow_runs.list_for_workflow(workflow_name, limit)

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
