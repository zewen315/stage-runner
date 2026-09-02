"""End-to-end scenarios against the real, running docker-compose stack --
every service, real Postgres/Redis/MinIO, driven entirely over the same
HTTP API the CLI and web UI use. Each of these mirrors a behavior that
was, at some point, verified by hand during development; here they're
automated and repeatable instead.

Slow by nature: the checked-in demo workflows each sleep 10s per stage
(so the Scheduler's dispatch is visible live when watched by a human) --
a full run is 30-40s+, and this file runs several. That's expected for
this layer; it's meant to run less often than the unit/integration
suites, not on every save.

Requires the stack already running (`docker compose up --build -d`) --
see conftest.py's `client` fixture for what happens if it isn't.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from conftest import trigger_and_wait, wait_for_dispatch, wait_for_schedule_terminal


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestHappyPath:
    def test_full_run_completes_and_promotes_every_stage(self, client, raw_events_current, completed_feed_success_run):
        result = completed_feed_success_run
        assert result["status"] == "completed"
        assert result["error"] is None

        stage_runs = client.get(f"/workflows/feed_success/runs/{result['run_id']}/stage-runs").json()
        by_name = {sr["stage_name"]: sr for sr in stage_runs}
        assert set(by_name) == {"aggregate_signals", "score_items", "rank_feed", "publish_feed"}

        for stage_name, stage_run in by_name.items():
            assert stage_run["status"] == "completed", stage_run
            assert stage_run["output_version"] is not None

            current = client.get(f"/resources/{stage_name}").json()
            assert current["version"]["version"] == stage_run["output_version"], (
                f"{stage_name}: run promoted v{stage_run['output_version']} but current is "
                f"v{current['version']['version']}"
            )


class TestBranching:
    def test_parallel_branches_dispatch_together_and_fan_in(self, client, raw_events_current):
        result = trigger_and_wait(client, "feed_branching", {"promote": True})
        assert result["status"] == "completed"

        stage_runs = client.get(f"/workflows/feed_branching/runs/{result['run_id']}/stage-runs").json()
        by_name = {sr["stage_name"]: sr for sr in stage_runs}

        rank_requested = datetime.fromisoformat(by_name["rank_feed"]["requested_at"])
        trending_requested = datetime.fromisoformat(by_name["trending_topics"]["requested_at"])
        assert abs((rank_requested - trending_requested).total_seconds()) < 2, (
            "rank_feed and trending_topics both depend only on score_items -- they should be "
            "dispatched in the same Scheduler tick, not one after the other"
        )

        publish = by_name["publish_feed"]
        assert set(publish["input_versions"]) == {"rank_feed", "trending_topics"}
        publish_requested = datetime.fromisoformat(publish["requested_at"])
        rank_finished = datetime.fromisoformat(by_name["rank_feed"]["finished_at"])
        trending_finished = datetime.fromisoformat(by_name["trending_topics"]["finished_at"])
        assert publish_requested >= rank_finished
        assert publish_requested >= trending_finished


class TestOnFailureFallback:
    def test_fallback_override_lets_a_halt_by_default_workflow_continue(
        self, client, raw_events_current, completed_feed_success_run
    ):
        # completed_feed_success_run guarantees score_items already has a
        # promoted version for feed_crash's own score_items failure to
        # fall back to -- resources are named globally, not per workflow.
        result = trigger_and_wait(client, "feed_crash", {"on_failure": "fallback"})
        assert result["status"] == "completed"

        stage_runs = client.get(f"/workflows/feed_crash/runs/{result['run_id']}/stage-runs").json()
        by_name = {sr["stage_name"]: sr for sr in stage_runs}

        assert by_name["score_items"]["status"] == "failed"
        assert by_name["score_items"]["used_fallback"] is True
        assert by_name["rank_feed"]["status"] == "completed"
        assert by_name["publish_feed"]["status"] == "completed"

    def test_halt_override_stops_a_fallback_by_default_workflow(self, client, raw_events_current):
        result = trigger_and_wait(client, "feed_fallback", {"on_failure": "halt"})
        assert result["status"] == "failed"


class TestCancellation:
    def test_cancelling_a_run_stops_further_dispatch(self, client, raw_events_current):
        schedule = client.post("/workflows/feed_success/runs", json={}).json()
        run_id = wait_for_dispatch(client, "feed_success", schedule["id"])

        client.post(f"/workflows/feed_success/runs/{run_id}/cancel").raise_for_status()
        final = wait_for_schedule_terminal(client, "feed_success", schedule["id"], timeout=30)
        assert final["status"] == "cancelled"

        stage_count = len(client.get(f"/workflows/feed_success/runs/{run_id}/stage-runs").json())
        time.sleep(15)  # longer than one stage's own 10s runtime
        assert len(client.get(f"/workflows/feed_success/runs/{run_id}/stage-runs").json()) == stage_count, (
            "no new stage should ever be dispatched for a cancelled run, even if one already "
            "in flight when cancelled keeps running to completion in the background"
        )

    def test_cancelling_a_pending_schedule_before_it_dispatches(self, client, raw_events_current):
        far_future = "2099-01-01T00:00:00+00:00"
        schedule = client.post("/workflows/feed_success/runs", json={"run_at": far_future}).json()

        client.post(f"/workflows/feed_success/schedules/{schedule['id']}/cancel").raise_for_status()

        status = client.get(f"/workflows/feed_success/schedules/{schedule['id']}").json()
        assert status["status"] == "cancelled"
        assert status["run_id"] is None


class TestRecurringSchedule:
    def test_interval_schedule_fires_and_stops_after_cancel(self, client, raw_events_current):
        before_create = _now_iso()
        recurring = client.post("/workflows/feed_success/recurring-schedules", json={"interval_seconds": 5}).json()

        time.sleep(8)
        fired = _runs_requested_since(client, "feed_success", before_create)
        assert len(fired) >= 1, "the recurring schedule should have fired at least once by now"

        client.post(f"/workflows/feed_success/recurring-schedules/{recurring['id']}/cancel").raise_for_status()
        after_cancel = _now_iso()
        time.sleep(8)

        assert _runs_requested_since(client, "feed_success", after_cancel) == []


def _runs_requested_since(client, workflow: str, checkpoint: str) -> list[dict]:
    runs = client.get(f"/workflows/{workflow}/runs?limit=50").json()
    return [r for r in runs if r["requested_at"] > checkpoint]
