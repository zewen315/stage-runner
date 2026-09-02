from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class WorkflowRun:
    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool
    status: RunStatus
    requested_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    cancel_requested: bool = False
    """Set by request_cancel(), acted on by the Scheduler (which alone
    changes `status`) on its next tick -- so this can briefly be true
    while status is still "running", the window between asking to stop
    and the Scheduler actually marking it cancelled."""
    on_failure: str | None = None
    """None means use the workflow's own code-declared StageRegistry
    default; "halt" or "fallback" overrides it for this run only."""


@dataclass(frozen=True)
class StageRun:
    id: int
    workflow_run_id: int
    workflow_name: str
    stage_name: str
    input_versions: dict[str, int]
    promote: bool
    output_version: int | None
    status: RunStatus
    requested_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    attempts: int = 1
    """How many times the Runner actually called the stage function --
    more than 1 only when the stage declares `retries` and an earlier
    attempt failed."""
    used_fallback: bool = False
    """True when this stage itself failed but on_failure="fallback"
    let the run continue by treating it as if it had produced its
    currently-promoted version instead -- so downstream stages (and
    this run) may be building on a stale value, not a fresh one."""


@dataclass(frozen=True)
class Schedule:
    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool | None
    requested_at: str
    run_at: str | None
    """None means eligible for dispatch as soon as the Scheduler sees it
    (today's only behavior); set means the Scheduler won't dispatch it
    before then."""
    dispatched_at: str | None
    run_id: int | None
    on_failure: str | None = None
    """None means use the workflow's own code-declared default; "halt" or
    "fallback" overrides it for the run this schedule dispatches to."""


@dataclass(frozen=True)
class RecurringSchedule:
    """A standing rule the Scheduler fires on a cadence, spawning a plain
    WorkflowRun each time (with these defaults) rather than a client
    triggering one directly. `enabled=False` is how one is cancelled --
    kept, not deleted, so a workflow's recurring history stays
    inspectable."""

    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool | None
    enabled: bool
    next_run_at: str
    created_at: str
    cron_expression: str | None = None
    interval_seconds: int | None = None
    """Exactly one of cron_expression/interval_seconds is set -- the
    former for a standard cron cadence, the latter for a fixed "every N
    seconds" cadence too short to express in cron's minute-level
    resolution (handy for demos/testing)."""
    on_failure: str | None = None


@dataclass(frozen=True)
class StageInfo:
    """A stage's name, its direct dependencies, and its declared retry
    count -- as declared in the workflow's own registry, not persisted
    anywhere, just a read through to the workflow's code."""

    name: str
    depends_on: list[str]
    retries: int


@dataclass(frozen=True)
class ScheduleStatus:
    """What get_schedule_status returns: the schedule itself, proxying the
    status/error of the WorkflowRun it dispatched to (if dispatched yet)."""

    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    run_at: str | None
    status: str
    error: str | None
    run_id: int | None
