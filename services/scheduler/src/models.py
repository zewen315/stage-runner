from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PendingSchedule:
    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool | None


@dataclass(frozen=True)
class DueRecurringSchedule:
    """A standing rule whose next_run_at has arrived -- fires by spawning
    a plain WorkflowRun with these defaults (see poller.py's
    _intake_recurring), the same way a one-off Schedule does once
    dispatched."""

    id: int
    workflow_name: str
    cron_expression: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool | None


@dataclass(frozen=True)
class ActiveWorkflowRun:
    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool
    status: str
    cancel_requested: bool = False


@dataclass(frozen=True)
class StageRunRecord:
    stage_name: str
    status: str
    output_version: int | None
    error: str | None
