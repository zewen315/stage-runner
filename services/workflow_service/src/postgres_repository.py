"""Postgres-backed RunRepository. Mirrors InMemoryRunRepository's behavior
exactly (see memory.py) -- just persisted. This service owns its own
database (a separate database from resource_store's, on the same Postgres
server in docker-compose) -- no service reaches into another's tables.
"""

from __future__ import annotations

import psycopg

from models import Run, RunStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id             BIGSERIAL PRIMARY KEY,
    workflow_name  TEXT NOT NULL,
    status         TEXT NOT NULL,
    requested_at   TIMESTAMPTZ NOT NULL,
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    error          TEXT
);
"""


class PostgresRunRepository:
    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    @staticmethod
    def _run_from_row(row) -> Run:
        return Run(
            id=row[0],
            workflow_name=row[1],
            status=RunStatus(row[2]),
            requested_at=row[3].isoformat(),
            started_at=row[4].isoformat() if row[4] else None,
            finished_at=row[5].isoformat() if row[5] else None,
            error=row[6],
        )

    def create(self, workflow_name: str, requested_at: str) -> Run:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (workflow_name, status, requested_at)
                VALUES (%s, %s, %s)
                RETURNING id, workflow_name, status, requested_at, started_at, finished_at, error
                """,
                (workflow_name, RunStatus.REQUESTED.value, requested_at),
            )
            return self._run_from_row(cur.fetchone())

    def get(self, workflow_name: str, run_id: int) -> Run | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, workflow_name, status, requested_at, started_at, finished_at, error
                FROM runs WHERE id = %s AND workflow_name = %s
                """,
                (run_id, workflow_name),
            )
            row = cur.fetchone()
        return self._run_from_row(row) if row else None

    def mark_running(self, run_id: int, started_at: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = %s, started_at = %s WHERE id = %s",
                (RunStatus.RUNNING.value, started_at, run_id),
            )

    def mark_completed(self, run_id: int, finished_at: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = %s, finished_at = %s WHERE id = %s",
                (RunStatus.COMPLETED.value, finished_at, run_id),
            )

    def mark_failed(self, run_id: int, finished_at: str, error: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = %s, finished_at = %s, error = %s WHERE id = %s",
                (RunStatus.FAILED.value, finished_at, error, run_id),
            )
