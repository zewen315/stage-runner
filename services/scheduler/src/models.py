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
    on_failure: str | None = None


@dataclass(frozen=True)
class DueRecurringSchedule:
    """A standing rule whose next_run_at has arrived -- fires by spawning
    a plain WorkflowRun with these defaults (see poller.py's
    _intake_recurring), the same way a one-off Schedule does once
    dispatched."""

    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool | None
    cron_expression: str | None = None
    interval_seconds: int | None = None
    """Exactly one is set -- see workflow_service's RecurringSchedule."""
    on_failure: str | None = None


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
    on_failure: str | None = None
    """None means use the workflow's own code-declared StageRegistry
    default; set overrides it for this run only."""


@dataclass(frozen=True)
class StageRunRecord:
    id: int
    stage_name: str
    status: str
    output_version: int | None
    error: str | None
    used_fallback: bool = False
