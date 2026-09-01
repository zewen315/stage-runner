from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


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


@dataclass(frozen=True)
class Schedule:
    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool | None
    requested_at: str
    dispatched_at: str | None
    run_id: int | None


@dataclass(frozen=True)
class StageInfo:
    """A stage's name and its direct dependencies, as declared in the
    workflow's own registry -- not persisted anywhere, just a read
    through to the workflow's code."""

    name: str
    depends_on: list[str]


@dataclass(frozen=True)
class ScheduleStatus:
    """What get_schedule_status returns: the schedule itself, proxying the
    status/error of the WorkflowRun it dispatched to (if dispatched yet)."""

    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    status: str
    error: str | None
    run_id: int | None
