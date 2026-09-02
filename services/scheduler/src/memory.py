from __future__ import annotations

from datetime import datetime, timezone

from models import ActiveWorkflowRun, PendingSchedule, StageRunRecord


class InMemoryScheduleStore:
    def __init__(self) -> None:
        self._schedules: dict[int, dict] = {}
        self._next_schedule_id = 1

        self._runs: dict[int, dict] = {}
        self._next_run_id = 1

        self._stage_runs: dict[int, dict] = {}
        self._next_stage_run_id = 1

    # -- test-seeding helpers --------------------------------------------

    def add_schedule(
        self,
        workflow_name: str,
        start_from: str | None = None,
        stop_after: str | None = None,
        input_versions: dict[str, int] | None = None,
        promote: bool | None = None,
        run_at: str | None = None,
    ) -> int:
        schedule_id = self._next_schedule_id
        self._schedules[schedule_id] = {
            "workflow_name": workflow_name,
            "start_from": start_from,
            "stop_after": stop_after,
            "input_versions": input_versions,
            "promote": promote,
            "run_at": run_at,
            "dispatched": False,
        }
        self._next_schedule_id += 1
        return schedule_id

    def add_workflow_run(
        self,
        workflow_name: str,
        start_from: str | None = None,
        stop_after: str | None = None,
        input_versions: dict[str, int] | None = None,
        promote: bool = True,
        status: str = "requested",
    ) -> int:
        run_id = self._next_run_id
        self._runs[run_id] = {
            "workflow_name": workflow_name,
            "start_from": start_from,
            "stop_after": stop_after,
            "input_versions": input_versions,
            "promote": promote,
            "status": status,
            "error": None,
        }
        self._next_run_id += 1
        return run_id

    def add_stage_run(
        self,
        workflow_run_id: int,
        stage_name: str,
        status: str = "requested",
        output_version: int | None = None,
        error: str | None = None,
    ) -> int:
        stage_run_id = self._next_stage_run_id
        self._stage_runs[stage_run_id] = {
            "workflow_run_id": workflow_run_id,
            "stage_name": stage_name,
            "status": status,
            "output_version": output_version,
            "error": error,
        }
        self._next_stage_run_id += 1
        return stage_run_id

    def set_stage_run_status(
        self, stage_run_id: int, status: str, output_version: int | None = None, error: str | None = None
    ) -> None:
        """Test helper: simulate the worker's start/complete/fail callback
        (which really lands on workflow_service, not this store)."""
        self._stage_runs[stage_run_id]["status"] = status
        self._stage_runs[stage_run_id]["output_version"] = output_version
        self._stage_runs[stage_run_id]["error"] = error

    # -- ScheduleStore protocol ------------------------------------------

    def pending_schedules(self) -> list[PendingSchedule]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            PendingSchedule(
                id=sid,
                workflow_name=s["workflow_name"],
                start_from=s["start_from"],
                stop_after=s["stop_after"],
                input_versions=s["input_versions"],
                promote=s["promote"],
            )
            for sid, s in self._schedules.items()
            if not s["dispatched"] and (s["run_at"] is None or s["run_at"] <= now)
        ]

    def mark_schedule_dispatched(self, schedule_id: int, *, run_id: int) -> None:
        self._schedules[schedule_id]["dispatched"] = True
        self._schedules[schedule_id]["run_id"] = run_id

    def create_workflow_run(
        self,
        workflow_name: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool,
    ) -> int:
        return self.add_workflow_run(
            workflow_name, start_from, stop_after, input_versions, promote
        )

    def create_stage_run(
        self,
        workflow_run_id: int,
        workflow_name: str,
        stage_name: str,
        input_versions: dict[str, int],
        promote: bool,
    ) -> int:
        return self.add_stage_run(workflow_run_id, stage_name)

    def active_workflow_runs(self) -> list[ActiveWorkflowRun]:
        return [
            ActiveWorkflowRun(
                id=rid,
                workflow_name=r["workflow_name"],
                start_from=r["start_from"],
                stop_after=r["stop_after"],
                input_versions=r["input_versions"],
                promote=r["promote"],
                status=r["status"],
            )
            for rid, r in self._runs.items()
            if r["status"] in ("requested", "running")
        ]

    def stage_runs_for_workflow_run(self, run_id: int) -> list[StageRunRecord]:
        return [
            StageRunRecord(
                stage_name=sr["stage_name"],
                status=sr["status"],
                output_version=sr["output_version"],
                error=sr["error"],
            )
            for sr in self._stage_runs.values()
            if sr["workflow_run_id"] == run_id
        ]

    def mark_workflow_run_running(self, run_id: int) -> None:
        self._runs[run_id]["status"] = "running"

    def mark_workflow_run_completed(self, run_id: int) -> None:
        self._runs[run_id]["status"] = "completed"

    def mark_workflow_run_failed(self, run_id: int, error: str) -> None:
        self._runs[run_id]["status"] = "failed"
        self._runs[run_id]["error"] = error


class InMemoryRunQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict] = []

    def enqueue_stage_run(
        self,
        stage_run_id: int,
        workflow_run_id: int,
        workflow_name: str,
        stage_name: str,
        input_versions: dict[str, int],
        promote: bool,
    ) -> None:
        self.enqueued.append(
            {
                "stage_run_id": stage_run_id,
                "workflow_run_id": workflow_run_id,
                "workflow_name": workflow_name,
                "stage_name": stage_name,
                "input_versions": input_versions,
                "promote": promote,
            }
        )
