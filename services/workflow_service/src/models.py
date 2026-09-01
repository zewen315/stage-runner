from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScheduleScope(str, Enum):
    WORKFLOW = "workflow"
    STAGE = "stage"


@dataclass(frozen=True)
class WorkflowRun:
    id: int
    workflow_name: str
    status: RunStatus
    requested_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None


@dataclass(frozen=True)
class StageRun:
    id: int
    workflow_run_id: int | None
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


@dataclass(frozen=True)
class Schedule:
    id: int
    workflow_name: str
    scope: ScheduleScope
    stage_name: str | None
    input_versions: dict[str, int] | None
    promote: bool | None
    requested_at: str
    dispatched_at: str | None
    run_id: int | None
    stage_run_id: int | None


@dataclass(frozen=True)
class ScheduleStatus:
    """What get_schedule_status returns: the schedule itself, proxying the
    status/error of whatever it dispatched to (if anything yet)."""

    id: int
    workflow_name: str
    scope: ScheduleScope
    stage_name: str | None
    status: str
    error: str | None
    run_id: int | None
    stage_run_id: int | None
