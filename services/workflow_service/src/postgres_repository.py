"""Postgres-backed ScheduleRepository, WorkflowRunRepository, and
StageRunRepository. This service owns the `workflow_service` database (a
separate database from resource_store's, on the same Postgres server in
docker-compose).

The Scheduler service also reads/writes `runs`/`stage_runs`/`schedules`
directly in this same database (it's the sole creator of `runs` and
`stage_runs` rows, and the only thing that ever changes a WorkflowRun's
status) -- that shared database is the intentional hand-off point between
this service and the Scheduler, the same role Redis plays between the
Scheduler and the Runner worker. No *other* service reaches into these
tables.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from models import RunStatus, Schedule, ScheduleScope, StageRun, WorkflowRun

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

CREATE TABLE IF NOT EXISTS stage_runs (
    id              BIGSERIAL PRIMARY KEY,
    workflow_run_id BIGINT REFERENCES runs(id),
    workflow_name   TEXT NOT NULL,
    stage_name      TEXT NOT NULL,
    input_versions  JSONB NOT NULL,
    promote         BOOLEAN NOT NULL,
    output_version  INTEGER,
    status          TEXT NOT NULL,
    requested_at    TIMESTAMPTZ NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id             BIGSERIAL PRIMARY KEY,
    workflow_name  TEXT NOT NULL,
    scope          TEXT NOT NULL,
    stage_name     TEXT,
    input_versions JSONB,
    promote        BOOLEAN,
    requested_at   TIMESTAMPTZ NOT NULL,
    dispatched_at  TIMESTAMPTZ,
    run_id         BIGINT REFERENCES runs(id),
    stage_run_id   BIGINT REFERENCES stage_runs(id)
);
"""


class PostgresScheduleRepository:
    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _schedule_from_row(row) -> Schedule:
        return Schedule(
            id=row[0],
            workflow_name=row[1],
            scope=ScheduleScope(row[2]),
            stage_name=row[3],
            input_versions=row[4],
            promote=row[5],
            requested_at=row[6].isoformat(),
            dispatched_at=row[7].isoformat() if row[7] else None,
            run_id=row[8],
            stage_run_id=row[9],
        )

    def create(
        self,
        workflow_name: str,
        scope: ScheduleScope,
        stage_name: str | None,
        input_versions: dict[str, int] | None,
        promote: bool | None,
        requested_at: str,
    ) -> Schedule:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO schedules (workflow_name, scope, stage_name, input_versions, promote, requested_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, workflow_name, scope, stage_name, input_versions, promote,
                          requested_at, dispatched_at, run_id, stage_run_id
                """,
                (
                    workflow_name,
                    scope.value,
                    stage_name,
                    Jsonb(input_versions) if input_versions is not None else None,
                    promote,
                    requested_at,
                ),
            )
            return self._schedule_from_row(cur.fetchone())

    def get(self, workflow_name: str, schedule_id: int) -> Schedule | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, workflow_name, scope, stage_name, input_versions, promote,
                       requested_at, dispatched_at, run_id, stage_run_id
                FROM schedules WHERE id = %s AND workflow_name = %s
                """,
                (schedule_id, workflow_name),
            )
            row = cur.fetchone()
        return self._schedule_from_row(row) if row else None


class PostgresWorkflowRunRepository:
    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _run_from_row(row) -> WorkflowRun:
        return WorkflowRun(
            id=row[0],
            workflow_name=row[1],
            status=RunStatus(row[2]),
            requested_at=row[3].isoformat(),
            started_at=row[4].isoformat() if row[4] else None,
            finished_at=row[5].isoformat() if row[5] else None,
            error=row[6],
        )

    def get(self, workflow_name: str, run_id: int) -> WorkflowRun | None:
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


class PostgresStageRunRepository:
    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _stage_run_from_row(row) -> StageRun:
        return StageRun(
            id=row[0],
            workflow_run_id=row[1],
            workflow_name=row[2],
            stage_name=row[3],
            input_versions=row[4],
            promote=row[5],
            output_version=row[6],
            status=RunStatus(row[7]),
            requested_at=row[8].isoformat(),
            started_at=row[9].isoformat() if row[9] else None,
            finished_at=row[10].isoformat() if row[10] else None,
            error=row[11],
        )

    _COLUMNS = (
        "id, workflow_run_id, workflow_name, stage_name, input_versions, promote, "
        "output_version, status, requested_at, started_at, finished_at, error"
    )

    def get(self, workflow_name: str, stage_run_id: int) -> StageRun | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLUMNS} FROM stage_runs WHERE id = %s AND workflow_name = %s",
                (stage_run_id, workflow_name),
            )
            row = cur.fetchone()
        return self._stage_run_from_row(row) if row else None

    def list_for_workflow_run(self, run_id: int) -> list[StageRun]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLUMNS} FROM stage_runs WHERE workflow_run_id = %s ORDER BY id",
                (run_id,),
            )
            return [self._stage_run_from_row(row) for row in cur.fetchall()]

    def mark_running(self, stage_run_id: int, started_at: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE stage_runs SET status = %s, started_at = %s WHERE id = %s",
                (RunStatus.RUNNING.value, started_at, stage_run_id),
            )

    def mark_completed(self, stage_run_id: int, finished_at: str, output_version: int | None) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE stage_runs SET status = %s, finished_at = %s, output_version = %s WHERE id = %s",
                (RunStatus.COMPLETED.value, finished_at, output_version, stage_run_id),
            )

    def mark_failed(self, stage_run_id: int, finished_at: str, error: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE stage_runs SET status = %s, finished_at = %s, error = %s WHERE id = %s",
                (RunStatus.FAILED.value, finished_at, error, stage_run_id),
            )
