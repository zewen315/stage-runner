from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PendingSchedule:
    id: int
    workflow_name: str
    scope: str  # 'workflow' | 'stage'
    stage_name: str | None
    input_versions: dict[str, int] | None
    promote: bool | None


@dataclass(frozen=True)
class ActiveWorkflowRun:
    id: int
    workflow_name: str
    status: str


@dataclass(frozen=True)
class StageRunRecord:
    stage_name: str
    status: str
    output_version: int | None
    error: str | None
