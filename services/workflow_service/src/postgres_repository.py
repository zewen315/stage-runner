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

from models import RecurringSchedule, RunStatus, Schedule, StageRun, WorkflowRun

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                BIGSERIAL PRIMARY KEY,
    workflow_name     TEXT NOT NULL,
    start_from        TEXT,
    stop_after        TEXT,
    input_versions    JSONB,
    promote           BOOLEAN NOT NULL,
    status            TEXT NOT NULL,
    requested_at      TIMESTAMPTZ NOT NULL,
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,
    error             TEXT,
    -- Set by workflow_service's request_cancel(); the Scheduler is still
    -- the only thing that ever changes `status`, on its next tick.
    cancel_requested  BOOLEAN NOT NULL DEFAULT false,
    -- NULL means use the workflow's own code-declared StageRegistry
    -- default; set overrides it for this run only. Copied from the
    -- schedule/recurring_schedule that spawned this run at intake time.
    on_failure        TEXT
);

CREATE TABLE IF NOT EXISTS stage_runs (
    id              BIGSERIAL PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL REFERENCES runs(id),
    workflow_name   TEXT NOT NULL,
    stage_name      TEXT NOT NULL,
    input_versions  JSONB NOT NULL,
    promote         BOOLEAN NOT NULL,
    output_version  INTEGER,
    status          TEXT NOT NULL,
    requested_at    TIMESTAMPTZ NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error           TEXT,
    -- Set by the worker's complete/fail callback; >1 only when the stage
    -- declares retries and an earlier attempt failed.
    attempts        INTEGER NOT NULL DEFAULT 1,
    -- Set directly by the Scheduler (not through this service) when this
    -- stage failed but on_failure="fallback" let the run continue anyway,
    -- treating it as if it had produced its currently-promoted version.
    used_fallback   BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS schedules (
    id             BIGSERIAL PRIMARY KEY,
    workflow_name  TEXT NOT NULL,
    start_from     TEXT,
    stop_after     TEXT,
    input_versions JSONB,
    promote        BOOLEAN,
    requested_at   TIMESTAMPTZ NOT NULL,
    -- NULL means eligible for dispatch as soon as the Scheduler sees it;
    -- set means the Scheduler won't dispatch it before then (see its
    -- pending_schedules() query).
    run_at         TIMESTAMPTZ,
    dispatched_at  TIMESTAMPTZ,
    run_id         BIGINT REFERENCES runs(id),
    -- NULL means use the workflow's own code-declared default; copied
    -- onto the WorkflowRun this schedule dispatches to.
    on_failure     TEXT,
    -- Set by request_schedule_cancel() before dispatch; the Scheduler's
    -- own pending_schedules() query excludes these, so a cancelled
    -- schedule simply never gets dispatched -- no status to write back.
    cancel_requested BOOLEAN NOT NULL DEFAULT false
);

-- A standing rule the Scheduler fires on a cadence -- distinct from
-- `schedules` above (a one-off trigger request): this table is never
-- "dispatched" itself, it just spawns a plain WorkflowRun each time
-- next_run_at comes due, via these same defaults.
CREATE TABLE IF NOT EXISTS recurring_schedules (
    id               BIGSERIAL PRIMARY KEY,
    workflow_name    TEXT NOT NULL,
    -- Exactly one of these two is set -- see RecurringSchedule in models.py.
    cron_expression  TEXT,
    interval_seconds INTEGER,
    start_from       TEXT,
    stop_after       TEXT,
    input_versions   JSONB,
    promote          BOOLEAN,
    enabled          BOOLEAN NOT NULL DEFAULT true,
    next_run_at      TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL,
    on_failure       TEXT
);
"""


class PostgresScheduleRepository:
    _COLUMNS = (
        "id, workflow_name, start_from, stop_after, input_versions, promote, "
        "requested_at, run_at, dispatched_at, run_id, on_failure, cancel_requested"
    )

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
            start_from=row[2],
            stop_after=row[3],
            input_versions=row[4],
            promote=row[5],
            requested_at=row[6].isoformat(),
            run_at=row[7].isoformat() if row[7] else None,
            dispatched_at=row[8].isoformat() if row[8] else None,
            run_id=row[9],
            on_failure=row[10],
            cancel_requested=row[11],
        )

    def create(
        self,
        workflow_name: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool | None,
        requested_at: str,
        run_at: str | None = None,
        on_failure: str | None = None,
    ) -> Schedule:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO schedules
                    (workflow_name, start_from, stop_after, input_versions, promote, requested_at,
                     run_at, on_failure)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {self._COLUMNS}
                """,
                (
                    workflow_name,
                    start_from,
                    stop_after,
                    Jsonb(input_versions) if input_versions is not None else None,
                    promote,
                    requested_at,
                    run_at,
                    on_failure,
                ),
            )
            return self._schedule_from_row(cur.fetchone())

    def get(self, workflow_name: str, schedule_id: int) -> Schedule | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLUMNS} FROM schedules WHERE id = %s AND workflow_name = %s",
                (schedule_id, workflow_name),
            )
            row = cur.fetchone()
        return self._schedule_from_row(row) if row else None

    def list_pending(self, workflow_name: str) -> list[Schedule]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {self._COLUMNS} FROM schedules
                WHERE workflow_name = %s AND dispatched_at IS NULL AND NOT cancel_requested
                ORDER BY id DESC
                """,
                (workflow_name,),
            )
            return [self._schedule_from_row(row) for row in cur.fetchall()]

    def request_cancel(self, schedule_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute("UPDATE schedules SET cancel_requested = true WHERE id = %s", (schedule_id,))


class PostgresRecurringScheduleRepository:
    _COLUMNS = (
        "id, workflow_name, start_from, stop_after, input_versions, promote, "
        "enabled, next_run_at, created_at, cron_expression, interval_seconds, on_failure"
    )

    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _recurring_from_row(row) -> RecurringSchedule:
        return RecurringSchedule(
            id=row[0],
            workflow_name=row[1],
            start_from=row[2],
            stop_after=row[3],
            input_versions=row[4],
            promote=row[5],
            enabled=row[6],
            next_run_at=row[7].isoformat(),
            created_at=row[8].isoformat(),
            cron_expression=row[9],
            interval_seconds=row[10],
            on_failure=row[11],
        )

    def create(
        self,
        workflow_name: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool | None,
        next_run_at: str,
        created_at: str,
        cron_expression: str | None = None,
        interval_seconds: int | None = None,
        on_failure: str | None = None,
    ) -> RecurringSchedule:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO recurring_schedules
                    (workflow_name, start_from, stop_after, input_versions, promote,
                     next_run_at, created_at, cron_expression, interval_seconds, on_failure)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {self._COLUMNS}
                """,
                (
                    workflow_name,
                    start_from,
                    stop_after,
                    Jsonb(input_versions) if input_versions is not None else None,
                    promote,
                    next_run_at,
                    created_at,
                    cron_expression,
                    interval_seconds,
                    on_failure,
                ),
            )
            return self._recurring_from_row(cur.fetchone())

    def get(self, workflow_name: str, recurring_schedule_id: int) -> RecurringSchedule | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLUMNS} FROM recurring_schedules WHERE id = %s AND workflow_name = %s",
                (recurring_schedule_id, workflow_name),
            )
            row = cur.fetchone()
        return self._recurring_from_row(row) if row else None

    def list_for_workflow(self, workflow_name: str) -> list[RecurringSchedule]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLUMNS} FROM recurring_schedules WHERE workflow_name = %s ORDER BY id",
                (workflow_name,),
            )
            return [self._recurring_from_row(row) for row in cur.fetchall()]

    def set_enabled(self, recurring_schedule_id: int, enabled: bool) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE recurring_schedules SET enabled = %s WHERE id = %s",
                (enabled, recurring_schedule_id),
            )


class PostgresWorkflowRunRepository:
    _COLUMNS = (
        "id, workflow_name, start_from, stop_after, input_versions, promote, "
        "status, requested_at, started_at, finished_at, error, cancel_requested, on_failure"
    )

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
            start_from=row[2],
            stop_after=row[3],
            input_versions=row[4],
            promote=row[5],
            status=RunStatus(row[6]),
            requested_at=row[7].isoformat(),
            started_at=row[8].isoformat() if row[8] else None,
            finished_at=row[9].isoformat() if row[9] else None,
            error=row[10],
            cancel_requested=row[11],
            on_failure=row[12],
        )

    def get(self, workflow_name: str, run_id: int) -> WorkflowRun | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLUMNS} FROM runs WHERE id = %s AND workflow_name = %s",
                (run_id, workflow_name),
            )
            row = cur.fetchone()
        return self._run_from_row(row) if row else None

    def list_for_workflow(self, workflow_name: str, limit: int) -> list[WorkflowRun]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLUMNS} FROM runs WHERE workflow_name = %s ORDER BY id DESC LIMIT %s",
                (workflow_name, limit),
            )
            return [self._run_from_row(row) for row in cur.fetchall()]

    def mark_cancel_requested(self, run_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute("UPDATE runs SET cancel_requested = true WHERE id = %s", (run_id,))


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
            attempts=row[12],
            used_fallback=row[13],
        )

    _COLUMNS = (
        "id, workflow_run_id, workflow_name, stage_name, input_versions, promote, "
        "output_version, status, requested_at, started_at, finished_at, error, attempts, used_fallback"
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

    def mark_completed(
        self, stage_run_id: int, finished_at: str, output_version: int | None, attempts: int = 1
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE stage_runs SET status = %s, finished_at = %s, output_version = %s, "
                "attempts = %s WHERE id = %s",
                (RunStatus.COMPLETED.value, finished_at, output_version, attempts, stage_run_id),
            )

    def mark_failed(self, stage_run_id: int, finished_at: str, error: str, attempts: int = 1) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE stage_runs SET status = %s, finished_at = %s, error = %s, attempts = %s WHERE id = %s",
                (RunStatus.FAILED.value, finished_at, error, attempts, stage_run_id),
            )
