"""Storage/queue interfaces the service depends on -- same reasoning as
resource_store's ports.py: depending on Protocols instead of concrete
clients keeps WorkflowService testable with fast in-memory fakes, with the
real Postgres/Redis adapters swapped in only when actually running.
"""

from __future__ import annotations

from typing import Protocol

from models import Run


class RunRepository(Protocol):
    def create(self, workflow_name: str, requested_at: str) -> Run: ...

    def get(self, workflow_name: str, run_id: int) -> Run | None: ...

    def mark_running(self, run_id: int, started_at: str) -> None: ...

    def mark_completed(self, run_id: int, finished_at: str) -> None: ...

    def mark_failed(self, run_id: int, finished_at: str, error: str) -> None: ...


class RunQueue(Protocol):
    def enqueue(self, run_id: int, workflow_name: str) -> None: ...
