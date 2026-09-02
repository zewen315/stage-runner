"""Integration tests: the four Postgres-backed repositories against a
real, ephemeral Postgres (testcontainers), not the InMemory* fakes every
other test in this suite uses. Exists to catch what those tests
structurally can't -- e.g. list_pending's `AND NOT cancel_requested`
clause, or a nullable-column migration -- since a fake just mirrors
Python dicts and can't be wrong about SQL.

workflow_service never creates `runs`/`stage_runs` rows itself (the
Scheduler is the sole creator, writing directly to the same database) --
those fixtures are seeded here with raw SQL, exactly the shape the
Scheduler's own writes take.

Excluded from the default `pytest` run (see pyproject.toml's addopts);
needs Docker. Run explicitly with `uv run pytest -m integration`.
"""

from __future__ import annotations

import pytest
from testcontainers.community.postgres import PostgresContainer

from models import RunStatus
from postgres_repository import (
    PostgresRecurringScheduleRepository,
    PostgresScheduleRepository,
    PostgresStageRunRepository,
    PostgresWorkflowRunRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgres:16") as container:
        yield container


def _dsn(postgres_container):
    return postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture
def schedules(postgres_container):
    repo = PostgresScheduleRepository(_dsn(postgres_container))
    yield repo
    _truncate(repo._conn)
    repo.close()


@pytest.fixture
def recurring_schedules(postgres_container):
    repo = PostgresRecurringScheduleRepository(_dsn(postgres_container))
    yield repo
    _truncate(repo._conn)
    repo.close()


@pytest.fixture
def workflow_runs(postgres_container):
    repo = PostgresWorkflowRunRepository(_dsn(postgres_container))
    yield repo
    _truncate(repo._conn)
    repo.close()


@pytest.fixture
def stage_runs(postgres_container):
    repo = PostgresStageRunRepository(_dsn(postgres_container))
    yield repo
    _truncate(repo._conn)
    repo.close()


def _truncate(conn):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE stage_runs, schedules, recurring_schedules, runs RESTART IDENTITY CASCADE")


def _seed_run(conn, **overrides) -> int:
    fields = {
        "workflow_name": "feed_ranking",
        "promote": True,
        "status": "requested",
        "on_failure": None,
        **overrides,
    }
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs (workflow_name, promote, status, requested_at, on_failure) "
            "VALUES (%s, %s, %s, now(), %s) RETURNING id",
            (fields["workflow_name"], fields["promote"], fields["status"], fields["on_failure"]),
        )
        return cur.fetchone()[0]


def _seed_stage_run(conn, run_id: int, **overrides) -> int:
    fields = {"workflow_name": "feed_ranking", "stage_name": "score_items", "promote": True, **overrides}
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO stage_runs "
            "(workflow_run_id, workflow_name, stage_name, input_versions, promote, status, requested_at) "
            "VALUES (%s, %s, %s, '{}', %s, 'requested', now()) RETURNING id",
            (run_id, fields["workflow_name"], fields["stage_name"], fields["promote"]),
        )
        return cur.fetchone()[0]


class TestScheduleRepository:
    def test_create_and_get(self, schedules):
        created = schedules.create("feed_ranking", None, None, None, None, requested_at="2026-01-01T00:00:00+00:00")
        fetched = schedules.get("feed_ranking", created.id)
        assert fetched.id == created.id
        assert fetched.dispatched_at is None
        assert fetched.cancel_requested is False

    def test_list_pending_excludes_cancelled_schedules(self, schedules):
        pending = schedules.create(
            "feed_ranking", None, None, None, None, requested_at="2026-01-01T00:00:00+00:00"
        )
        cancelled = schedules.create(
            "feed_ranking", None, None, None, None, requested_at="2026-01-01T00:00:00+00:00"
        )
        schedules.request_cancel(cancelled.id)

        ids = [s.id for s in schedules.list_pending("feed_ranking")]

        assert pending.id in ids
        assert cancelled.id not in ids

    def test_request_cancel_is_visible_via_get_even_though_excluded_from_pending(self, schedules):
        created = schedules.create(
            "feed_ranking", None, None, None, None, requested_at="2026-01-01T00:00:00+00:00"
        )
        schedules.request_cancel(created.id)
        assert schedules.get("feed_ranking", created.id).cancel_requested is True


class TestRecurringScheduleRepository:
    def test_create_with_cron_expression(self, recurring_schedules):
        created = recurring_schedules.create(
            "feed_ranking",
            None,
            None,
            None,
            None,
            next_run_at="2026-01-01T01:00:00+00:00",
            created_at="2026-01-01T00:00:00+00:00",
            cron_expression="0 * * * *",
        )
        assert created.cron_expression == "0 * * * *"
        assert created.interval_seconds is None

    def test_create_with_interval_seconds(self, recurring_schedules):
        created = recurring_schedules.create(
            "feed_ranking",
            None,
            None,
            None,
            None,
            next_run_at="2026-01-01T00:01:00+00:00",
            created_at="2026-01-01T00:00:00+00:00",
            interval_seconds=60,
        )
        assert created.interval_seconds == 60
        assert created.cron_expression is None

    def test_set_enabled_false_is_visible_via_list(self, recurring_schedules):
        created = recurring_schedules.create(
            "feed_ranking",
            None,
            None,
            None,
            None,
            next_run_at="2026-01-01T00:01:00+00:00",
            created_at="2026-01-01T00:00:00+00:00",
            interval_seconds=60,
        )
        recurring_schedules.set_enabled(created.id, False)
        [fetched] = recurring_schedules.list_for_workflow("feed_ranking")
        assert fetched.enabled is False


class TestWorkflowRunRepository:
    def test_get_returns_the_seeded_row(self, workflow_runs):
        run_id = _seed_run(workflow_runs._conn, status="running")
        fetched = workflow_runs.get("feed_ranking", run_id)
        assert fetched.status == RunStatus.RUNNING

    def test_get_scoped_to_workflow_name_returns_none_for_a_mismatch(self, workflow_runs):
        run_id = _seed_run(workflow_runs._conn)
        assert workflow_runs.get("some_other_workflow", run_id) is None

    def test_list_for_workflow_orders_most_recent_first(self, workflow_runs):
        first = _seed_run(workflow_runs._conn)
        second = _seed_run(workflow_runs._conn)
        assert [r.id for r in workflow_runs.list_for_workflow("feed_ranking", limit=10)] == [second, first]

    def test_mark_cancel_requested(self, workflow_runs):
        run_id = _seed_run(workflow_runs._conn)
        workflow_runs.mark_cancel_requested(run_id)
        assert workflow_runs.get("feed_ranking", run_id).cancel_requested is True


class TestStageRunRepository:
    def test_mark_completed_records_attempts_and_output_version(self, stage_runs):
        run_id = _seed_run(stage_runs._conn)
        stage_run_id = _seed_stage_run(stage_runs._conn, run_id)

        stage_runs.mark_completed(stage_run_id, finished_at="2026-01-01T00:01:00+00:00", output_version=3, attempts=2)

        fetched = stage_runs.get("feed_ranking", stage_run_id)
        assert fetched.status == RunStatus.COMPLETED
        assert fetched.output_version == 3
        assert fetched.attempts == 2

    def test_mark_failed_records_error(self, stage_runs):
        run_id = _seed_run(stage_runs._conn)
        stage_run_id = _seed_stage_run(stage_runs._conn, run_id)

        stage_runs.mark_failed(stage_run_id, finished_at="2026-01-01T00:01:00+00:00", error="boom", attempts=3)

        fetched = stage_runs.get("feed_ranking", stage_run_id)
        assert fetched.status == RunStatus.FAILED
        assert fetched.error == "boom"
        assert fetched.attempts == 3

    def test_list_for_workflow_run_returns_only_that_runs_stages(self, stage_runs):
        run_a = _seed_run(stage_runs._conn)
        run_b = _seed_run(stage_runs._conn)
        stage_a = _seed_stage_run(stage_runs._conn, run_a)
        _seed_stage_run(stage_runs._conn, run_b)

        result = stage_runs.list_for_workflow_run(run_a)

        assert [sr.id for sr in result] == [stage_a]
