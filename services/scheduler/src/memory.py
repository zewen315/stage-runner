from __future__ import annotations

from datetime import datetime, timezone

from models import ActiveWorkflowRun, DueRecurringSchedule, PendingSchedule, StageRunRecord


class InMemoryScheduleStore:
    def __init__(self) -> None:
        self._schedules: dict[int, dict] = {}
        self._next_schedule_id = 1

        self._runs: dict[int, dict] = {}
        self._next_run_id = 1

        self._stage_runs: dict[int, dict] = {}
        self._next_stage_run_id = 1

        self._recurring_schedules: dict[int, dict] = {}
        self._next_recurring_schedule_id = 1

    # -- test-seeding helpers --------------------------------------------

    def add_schedule(
        self,
        workflow_name: str,
        start_from: str | None = None,
        stop_after: str | None = None,
        input_versions: dict[str, int] | None = None,
        promote: bool | None = None,
        run_at: str | None = None,
        on_failure: str | None = None,
        cancel_requested: bool = False,
    ) -> int:
        schedule_id = self._next_schedule_id
        self._schedules[schedule_id] = {
            "workflow_name": workflow_name,
            "start_from": start_from,
            "stop_after": stop_after,
            "input_versions": input_versions,
            "promote": promote,
            "run_at": run_at,
            "on_failure": on_failure,
            "cancel_requested": cancel_requested,
            "dispatched": False,
        }
        self._next_schedule_id += 1
        return schedule_id

    def add_recurring_schedule(
        self,
        workflow_name: str,
        cron_expression: str | None = "* * * * *",
        start_from: str | None = None,
        stop_after: str | None = None,
        input_versions: dict[str, int] | None = None,
        promote: bool | None = None,
        next_run_at: str | None = None,
        enabled: bool = True,
        interval_seconds: int | None = None,
        on_failure: str | None = None,
    ) -> int:
        if interval_seconds is not None:
            cron_expression = None
        recurring_schedule_id = self._next_recurring_schedule_id
        self._recurring_schedules[recurring_schedule_id] = {
            "workflow_name": workflow_name,
            "cron_expression": cron_expression,
            "interval_seconds": interval_seconds,
            "start_from": start_from,
            "stop_after": stop_after,
            "input_versions": input_versions,
            "promote": promote,
            "next_run_at": next_run_at or datetime.now(timezone.utc).isoformat(),
            "enabled": enabled,
            "on_failure": on_failure,
        }
        self._next_recurring_schedule_id += 1
        return recurring_schedule_id

    def add_workflow_run(
        self,
        workflow_name: str,
        start_from: str | None = None,
        stop_after: str | None = None,
        input_versions: dict[str, int] | None = None,
        promote: bool = True,
        status: str = "requested",
        cancel_requested: bool = False,
        on_failure: str | None = None,
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
            "cancel_requested": cancel_requested,
            "on_failure": on_failure,
        }
        self._next_run_id += 1
        return run_id

    def request_cancel(self, run_id: int) -> None:
        """Test-seeding helper: real cancellation requests land on
        workflow_service, not this store -- tests use this to simulate
        "a cancel was already requested" ahead of a poll."""
        self._runs[run_id]["cancel_requested"] = True

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
            "used_fallback": False,
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
                on_failure=s["on_failure"],
            )
            for sid, s in self._schedules.items()
            if not s["dispatched"] and (s["run_at"] is None or s["run_at"] <= now) and not s["cancel_requested"]
        ]

    def mark_schedule_dispatched(self, schedule_id: int, *, run_id: int) -> None:
        self._schedules[schedule_id]["dispatched"] = True
        self._schedules[schedule_id]["run_id"] = run_id

    def due_recurring_schedules(self) -> list[DueRecurringSchedule]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            DueRecurringSchedule(
                id=rid,
                workflow_name=r["workflow_name"],
                cron_expression=r["cron_expression"],
                interval_seconds=r["interval_seconds"],
                start_from=r["start_from"],
                stop_after=r["stop_after"],
                input_versions=r["input_versions"],
                promote=r["promote"],
                on_failure=r["on_failure"],
            )
            for rid, r in self._recurring_schedules.items()
            if r["enabled"] and r["next_run_at"] <= now
        ]

    def advance_recurring_schedule(self, recurring_schedule_id: int, next_run_at: str) -> None:
        self._recurring_schedules[recurring_schedule_id]["next_run_at"] = next_run_at

    def create_workflow_run(
        self,
        workflow_name: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool,
        on_failure: str | None = None,
    ) -> int:
        return self.add_workflow_run(
            workflow_name, start_from, stop_after, input_versions, promote, on_failure=on_failure
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
                cancel_requested=r["cancel_requested"],
                on_failure=r["on_failure"],
            )
            for rid, r in self._runs.items()
            if r["status"] in ("requested", "running")
        ]

    def stage_runs_for_workflow_run(self, run_id: int) -> list[StageRunRecord]:
        return [
            StageRunRecord(
                id=sid,
                stage_name=sr["stage_name"],
                status=sr["status"],
                output_version=sr["output_version"],
                error=sr["error"],
                used_fallback=sr["used_fallback"],
            )
            for sid, sr in self._stage_runs.items()
            if sr["workflow_run_id"] == run_id
        ]

    def mark_stage_run_used_fallback(self, stage_run_id: int) -> None:
        self._stage_runs[stage_run_id]["used_fallback"] = True

    def mark_workflow_run_running(self, run_id: int) -> None:
        self._runs[run_id]["status"] = "running"

    def mark_workflow_run_completed(self, run_id: int) -> None:
        self._runs[run_id]["status"] = "completed"

    def mark_workflow_run_failed(self, run_id: int, error: str) -> None:
        self._runs[run_id]["status"] = "failed"
        self._runs[run_id]["error"] = error

    def mark_workflow_run_cancelled(self, run_id: int) -> None:
        self._runs[run_id]["status"] = "cancelled"


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
