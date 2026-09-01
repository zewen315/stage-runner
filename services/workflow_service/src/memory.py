from __future__ import annotations

from dataclasses import replace

from models import RunStatus, Schedule, StageRun, WorkflowRun


class InMemoryScheduleRepository:
    def __init__(self) -> None:
        self._schedules: dict[int, Schedule] = {}
        self._next_id = 1

    def create(
        self,
        workflow_name: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool | None,
        requested_at: str,
    ) -> Schedule:
        schedule = Schedule(
            id=self._next_id,
            workflow_name=workflow_name,
            start_from=start_from,
            stop_after=stop_after,
            input_versions=input_versions,
            promote=promote,
            requested_at=requested_at,
            dispatched_at=None,
            run_id=None,
        )
        self._schedules[schedule.id] = schedule
        self._next_id += 1
        return schedule

    def get(self, workflow_name: str, schedule_id: int) -> Schedule | None:
        schedule = self._schedules.get(schedule_id)
        if schedule is None or schedule.workflow_name != workflow_name:
            return None
        return schedule

    def mark_dispatched(self, schedule_id: int, *, dispatched_at: str, run_id: int) -> None:
        """Test-seeding helper: real dispatch happens in the Scheduler
        service against its own Postgres store, not through this
        repository -- tests use this to simulate "already dispatched"."""
        self._schedules[schedule_id] = replace(
            self._schedules[schedule_id], dispatched_at=dispatched_at, run_id=run_id
        )


class InMemoryWorkflowRunRepository:
    def __init__(self) -> None:
        self._runs: dict[int, WorkflowRun] = {}

    def add(self, run: WorkflowRun) -> None:
        """Test-seeding helper -- see InMemoryScheduleRepository.mark_dispatched."""
        self._runs[run.id] = run

    def get(self, workflow_name: str, run_id: int) -> WorkflowRun | None:
        run = self._runs.get(run_id)
        if run is None or run.workflow_name != workflow_name:
            return None
        return run


class InMemoryStageRunRepository:
    def __init__(self) -> None:
        self._stage_runs: dict[int, StageRun] = {}

    def add(self, stage_run: StageRun) -> None:
        """Test-seeding helper -- see InMemoryScheduleRepository.mark_dispatched."""
        self._stage_runs[stage_run.id] = stage_run

    def get(self, workflow_name: str, stage_run_id: int) -> StageRun | None:
        stage_run = self._stage_runs.get(stage_run_id)
        if stage_run is None or stage_run.workflow_name != workflow_name:
            return None
        return stage_run

    def list_for_workflow_run(self, run_id: int) -> list[StageRun]:
        return sorted(
            (sr for sr in self._stage_runs.values() if sr.workflow_run_id == run_id),
            key=lambda sr: sr.id,
        )

    def mark_running(self, stage_run_id: int, started_at: str) -> None:
        self._stage_runs[stage_run_id] = replace(
            self._stage_runs[stage_run_id], status=RunStatus.RUNNING, started_at=started_at
        )

    def mark_completed(self, stage_run_id: int, finished_at: str, output_version: int | None) -> None:
        self._stage_runs[stage_run_id] = replace(
            self._stage_runs[stage_run_id],
            status=RunStatus.COMPLETED,
            finished_at=finished_at,
            output_version=output_version,
        )

    def mark_failed(self, stage_run_id: int, finished_at: str, error: str) -> None:
        self._stage_runs[stage_run_id] = replace(
            self._stage_runs[stage_run_id], status=RunStatus.FAILED, finished_at=finished_at, error=error
        )
