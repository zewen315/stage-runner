"""Postgres-backed ScheduleStore: reads and writes the same `schedules`,
`runs`, and `stage_runs` tables workflow_service owns, in its
`workflow_service` database. That shared database is the intended hand-off
point between workflow_service and the Scheduler -- the same role Redis
plays between the Scheduler and the Runner worker. Self-inits schema
(idempotent `CREATE TABLE IF NOT EXISTS`, identical to workflow_service's
own) so startup order between the two services doesn't matter.

The Scheduler is the sole creator of `runs`/`stage_runs` rows and the only
thing that ever changes a WorkflowRun's status.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from models import ActiveWorkflowRun, DueRecurringSchedule, PendingSchedule, StageRunRecord

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
    cancel_requested  BOOLEAN NOT NULL DEFAULT false
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
    error           TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id             BIGSERIAL PRIMARY KEY,
    workflow_name  TEXT NOT NULL,
    start_from     TEXT,
    stop_after     TEXT,
    input_versions JSONB,
    promote        BOOLEAN,
    requested_at   TIMESTAMPTZ NOT NULL,
    run_at         TIMESTAMPTZ,
    dispatched_at  TIMESTAMPTZ,
    run_id         BIGINT REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS recurring_schedules (
    id              BIGSERIAL PRIMARY KEY,
    workflow_name   TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    start_from      TEXT,
    stop_after      TEXT,
    input_versions  JSONB,
    promote         BOOLEAN,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    next_run_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL
);
"""


class PostgresScheduleStore:
    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def pending_schedules(self) -> list[PendingSchedule]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, workflow_name, start_from, stop_after, input_versions, promote "
                "FROM schedules WHERE dispatched_at IS NULL AND (run_at IS NULL OR run_at <= now())"
            )
            return [
                PendingSchedule(
                    id=row[0],
                    workflow_name=row[1],
                    start_from=row[2],
                    stop_after=row[3],
                    input_versions=row[4],
                    promote=row[5],
                )
                for row in cur.fetchall()
            ]

    def mark_schedule_dispatched(self, schedule_id: int, *, run_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE schedules SET dispatched_at = now(), run_id = %s WHERE id = %s",
                (run_id, schedule_id),
            )

    def due_recurring_schedules(self) -> list[DueRecurringSchedule]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, workflow_name, cron_expression, start_from, stop_after, input_versions, promote "
                "FROM recurring_schedules WHERE enabled AND next_run_at <= now()"
            )
            return [
                DueRecurringSchedule(
                    id=row[0],
                    workflow_name=row[1],
                    cron_expression=row[2],
                    start_from=row[3],
                    stop_after=row[4],
                    input_versions=row[5],
                    promote=row[6],
                )
                for row in cur.fetchall()
            ]

    def advance_recurring_schedule(self, recurring_schedule_id: int, next_run_at: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE recurring_schedules SET next_run_at = %s WHERE id = %s",
                (next_run_at, recurring_schedule_id),
            )

    def create_workflow_run(
        self,
        workflow_name: str,
        start_from: str | None,
        stop_after: str | None,
        input_versions: dict[str, int] | None,
        promote: bool,
    ) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (workflow_name, start_from, stop_after, input_versions, promote, status, requested_at)
                VALUES (%s, %s, %s, %s, %s, 'requested', now())
                RETURNING id
                """,
                (
                    workflow_name,
                    start_from,
                    stop_after,
                    Jsonb(input_versions) if input_versions is not None else None,
                    promote,
                ),
            )
            return cur.fetchone()[0]

    def create_stage_run(
        self,
        workflow_run_id: int,
        workflow_name: str,
        stage_name: str,
        input_versions: dict[str, int],
        promote: bool,
    ) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stage_runs
                    (workflow_run_id, workflow_name, stage_name, input_versions, promote, status, requested_at)
                VALUES (%s, %s, %s, %s, %s, 'requested', now())
                RETURNING id
                """,
                (workflow_run_id, workflow_name, stage_name, Jsonb(input_versions), promote),
            )
            return cur.fetchone()[0]

    def active_workflow_runs(self) -> list[ActiveWorkflowRun]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, workflow_name, start_from, stop_after, input_versions, promote, status, "
                "cancel_requested FROM runs WHERE status IN ('requested', 'running')"
            )
            return [
                ActiveWorkflowRun(
                    id=row[0],
                    workflow_name=row[1],
                    start_from=row[2],
                    stop_after=row[3],
                    input_versions=row[4],
                    promote=row[5],
                    status=row[6],
                    cancel_requested=row[7],
                )
                for row in cur.fetchall()
            ]

    def stage_runs_for_workflow_run(self, run_id: int) -> list[StageRunRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT stage_name, status, output_version, error FROM stage_runs WHERE workflow_run_id = %s",
                (run_id,),
            )
            return [
                StageRunRecord(stage_name=row[0], status=row[1], output_version=row[2], error=row[3])
                for row in cur.fetchall()
            ]

    def mark_workflow_run_running(self, run_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute("UPDATE runs SET status = 'running', started_at = now() WHERE id = %s", (run_id,))

    def mark_workflow_run_completed(self, run_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute("UPDATE runs SET status = 'completed', finished_at = now() WHERE id = %s", (run_id,))

    def mark_workflow_run_failed(self, run_id: int, error: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = 'failed', finished_at = now(), error = %s WHERE id = %s",
                (error, run_id),
            )

    def mark_workflow_run_cancelled(self, run_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET status = 'cancelled', finished_at = now() WHERE id = %s", (run_id,)
            )
