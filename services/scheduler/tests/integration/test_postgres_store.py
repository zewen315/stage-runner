"""Integration tests: PostgresScheduleStore against a real, ephemeral
Postgres (testcontainers), not the InMemoryScheduleStore fake every other
test in this suite uses. Exists to catch what those tests structurally
can't -- the actual SQL, in particular the eligibility predicates that
decide what gets dispatched (`pending_schedules`' cancel/run_at handling,
`due_recurring_schedules`' enabled/next_run_at check).

The Scheduler never creates `schedules`/`recurring_schedules` rows itself
(workflow_service does, over HTTP) -- those fixtures are seeded here with
raw SQL, exactly the shape workflow_service's own inserts take.

Excluded from the default `pytest` run (see pyproject.toml's addopts);
needs Docker. Run explicitly with `uv run pytest -m integration`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from testcontainers.community.postgres import PostgresContainer

from postgres_store import PostgresScheduleStore

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgres:16") as container:
        yield container


@pytest.fixture
def store(postgres_container):
    dsn = postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
    store = PostgresScheduleStore(dsn)
    yield store
    with store._conn.cursor() as cur:
        cur.execute("TRUNCATE stage_runs, schedules, recurring_schedules, runs RESTART IDENTITY CASCADE")
    store.close()


def _in(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def _seed_schedule(conn, *, run_at=None, cancel_requested=False) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schedules (workflow_name, promote, requested_at, run_at, cancel_requested) "
            "VALUES ('feed_ranking', true, now(), %s, %s) RETURNING id",
            (run_at, cancel_requested),
        )
        return cur.fetchone()[0]


def _seed_recurring(conn, *, enabled=True, next_run_at, cron_expression=None, interval_seconds=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO recurring_schedules "
            "(workflow_name, promote, enabled, next_run_at, created_at, cron_expression, interval_seconds) "
            "VALUES ('feed_ranking', true, %s, %s, now(), %s, %s) RETURNING id",
            (enabled, next_run_at, cron_expression, interval_seconds),
        )
        return cur.fetchone()[0]


class TestPendingSchedules:
    def test_undispatched_due_schedule_is_pending(self, store):
        _seed_schedule(store._conn)
        assert len(store.pending_schedules()) == 1

    def test_future_run_at_is_not_pending(self, store):
        _seed_schedule(store._conn, run_at=_in(timedelta(hours=1)))
        assert store.pending_schedules() == []

    def test_past_run_at_is_pending(self, store):
        _seed_schedule(store._conn, run_at=_in(-timedelta(hours=1)))
        assert len(store.pending_schedules()) == 1

    def test_cancelled_schedule_is_never_pending(self, store):
        _seed_schedule(store._conn, cancel_requested=True)
        assert store.pending_schedules() == []

    def test_mark_dispatched_removes_it_from_pending(self, store):
        schedule_id = _seed_schedule(store._conn)
        run_id = store.create_workflow_run("feed_ranking", None, None, None, True)

        store.mark_schedule_dispatched(schedule_id, run_id=run_id)

        assert store.pending_schedules() == []


class TestDueRecurringSchedules:
    def test_due_and_enabled_is_returned(self, store):
        _seed_recurring(store._conn, next_run_at=_in(-timedelta(minutes=1)), interval_seconds=60)
        assert len(store.due_recurring_schedules()) == 1

    def test_not_yet_due_is_excluded(self, store):
        _seed_recurring(store._conn, next_run_at=_in(timedelta(hours=1)), interval_seconds=60)
        assert store.due_recurring_schedules() == []

    def test_disabled_is_excluded_even_if_due(self, store):
        _seed_recurring(store._conn, enabled=False, next_run_at=_in(-timedelta(minutes=1)), interval_seconds=60)
        assert store.due_recurring_schedules() == []

    def test_advance_recurring_schedule_moves_next_run_at_out_of_range(self, store):
        recurring_id = _seed_recurring(store._conn, next_run_at=_in(-timedelta(minutes=1)), interval_seconds=60)
        store.advance_recurring_schedule(recurring_id, _in(timedelta(hours=1)))
        assert store.due_recurring_schedules() == []

    def test_carries_cron_and_interval_through_correctly(self, store):
        _seed_recurring(store._conn, next_run_at=_in(-timedelta(minutes=1)), cron_expression="0 * * * *")
        [due] = store.due_recurring_schedules()
        assert due.cron_expression == "0 * * * *"
        assert due.interval_seconds is None


class TestWorkflowRunLifecycle:
    def test_create_workflow_run_is_active(self, store):
        run_id = store.create_workflow_run("feed_ranking", None, None, None, True)
        [active] = store.active_workflow_runs()
        assert active.id == run_id
        assert active.status == "requested"

    def test_completed_run_is_no_longer_active(self, store):
        run_id = store.create_workflow_run("feed_ranking", None, None, None, True)
        store.mark_workflow_run_completed(run_id)
        assert store.active_workflow_runs() == []

    def test_failed_run_is_no_longer_active(self, store):
        run_id = store.create_workflow_run("feed_ranking", None, None, None, True)
        store.mark_workflow_run_failed(run_id, error="boom")
        assert store.active_workflow_runs() == []

    def test_running_status_transition(self, store):
        run_id = store.create_workflow_run("feed_ranking", None, None, None, True)
        store.mark_workflow_run_running(run_id)
        [active] = store.active_workflow_runs()
        assert active.status == "running"

    def test_cancelled_run_is_no_longer_active(self, store):
        run_id = store.create_workflow_run("feed_ranking", None, None, None, True)
        store.mark_workflow_run_cancelled(run_id)
        assert store.active_workflow_runs() == []


class TestStageRuns:
    def test_used_fallback_is_recorded_and_visible(self, store):
        run_id = store.create_workflow_run("feed_ranking", None, None, None, True)
        stage_run_id = store.create_stage_run(run_id, "feed_ranking", "score_items", {}, True)

        store.mark_stage_run_used_fallback(stage_run_id)

        [fetched] = store.stage_runs_for_workflow_run(run_id)
        assert fetched.used_fallback is True

    def test_stage_runs_scoped_to_their_own_workflow_run(self, store):
        run_a = store.create_workflow_run("feed_ranking", None, None, None, True)
        run_b = store.create_workflow_run("feed_ranking", None, None, None, True)
        store.create_stage_run(run_a, "feed_ranking", "score_items", {}, True)
        store.create_stage_run(run_b, "feed_ranking", "score_items", {}, True)

        assert len(store.stage_runs_for_workflow_run(run_a)) == 1
