from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class Run:
    id: int
    workflow_name: str
    status: RunStatus
    requested_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
