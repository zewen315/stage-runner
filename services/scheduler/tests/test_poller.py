from datetime import datetime, timedelta, timezone

from resource_store_client import InMemoryResourceClient
from stages import StageRegistry

from memory import InMemoryRunQueue, InMemoryScheduleStore
from poller import poll_once


def _in(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def _poll(store, queue, registry_provider, resources=None):
    """Most tests don't care about resource_store fallback lookups -- default
    to an empty fake so call sites don't all need one. TestFallback below
    passes a pre-seeded one directly to `poll_once`."""
    poll_once(store, queue, registry_provider, resources or InMemoryResourceClient())


def _linear_registry() -> StageRegistry:
    """raw -> doubled -> tripled, a simple two-hop chain."""
    registry = StageRegistry()
    registry.stage("raw")(lambda: None)

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return raw * 2

    @registry.stage("tripled", depends_on=["doubled"])
    def tripled(doubled):
        return doubled * 3

    return registry


def _branching_registry() -> StageRegistry:
    """raw -> doubled -> {tripled, quadrupled} (both depend on doubled)."""
    registry = StageRegistry()
    registry.stage("raw")(lambda: None)

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return raw * 2

    @registry.stage("tripled", depends_on=["doubled"])
    def tripled(doubled):
        return doubled * 3

    @registry.stage("quadrupled", depends_on=["doubled"])
    def quadrupled(doubled):
        return doubled * 4

    return registry


def _registry_with_injected_root() -> StageRegistry:
    """"raw" has no stage at all -- a workflow root with no producer,
    expected to already exist in the Resource Store (injected directly,
    not run)."""
    registry = StageRegistry()

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return raw * 2

    return registry


def _registry_provider(registry: StageRegistry):
    return lambda workflow_name: registry


class TestIntake:
    def test_full_run_schedule_creates_a_run_and_dispatches_the_root(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert len(store.active_workflow_runs()) == 1
        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]
        assert queue.enqueued[0]["workflow_run_id"] == store.active_workflow_runs()[0].id
        assert queue.enqueued[0]["promote"] is True

    def test_single_stage_schedule_creates_a_run_and_dispatches_immediately(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule(
            "feed_ranking", start_from="doubled", stop_after="doubled", input_versions={"raw": 5}
        )

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert len(queue.enqueued) == 1
        message = queue.enqueued[0]
        assert message["stage_name"] == "doubled"
        assert message["input_versions"] == {"raw": 5}
        assert message["promote"] is False  # partial-run default


class TestRunAt:
    def test_future_run_at_is_not_dispatched(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking", run_at=_in(timedelta(hours=1)))

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []

    def test_past_run_at_is_dispatched(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking", run_at=_in(-timedelta(hours=1)))

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]

    def test_no_run_at_is_dispatched_immediately(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]


class TestRecurringIntake:
    def test_due_recurring_schedule_spawns_a_run_and_dispatches(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_recurring_schedule("feed_ranking", next_run_at=_in(-timedelta(minutes=1)))

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert len(store.active_workflow_runs()) == 1
        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]

    def test_recurring_schedule_uses_its_own_run_shape_defaults(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_recurring_schedule(
            "feed_ranking",
            start_from="doubled",
            stop_after="doubled",
            input_versions={"raw": 5},
            next_run_at=_in(-timedelta(minutes=1)),
        )

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["doubled"]
        assert queue.enqueued[0]["input_versions"] == {"raw": 5}

    def test_not_yet_due_recurring_schedule_does_not_fire(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_recurring_schedule("feed_ranking", next_run_at=_in(timedelta(hours=1)))

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert store.active_workflow_runs() == []
        assert queue.enqueued == []

    def test_disabled_recurring_schedule_never_fires(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_recurring_schedule(
            "feed_ranking", next_run_at=_in(-timedelta(minutes=1)), enabled=False
        )

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert store.active_workflow_runs() == []

    def test_firing_advances_next_run_at_so_it_does_not_refire_immediately(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_recurring_schedule(
            "feed_ranking", cron_expression="* * * * *", next_run_at=_in(-timedelta(minutes=1))
        )

        _poll(store, queue, _registry_provider(_linear_registry()))
        assert len(store.active_workflow_runs()) == 1

        _poll(store, queue, _registry_provider(_linear_registry()))
        assert len(store.active_workflow_runs()) == 1  # no second run spawned this tick


class TestPromoteResolution:
    def test_full_run_defaults_promote_true(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued[0]["promote"] is True

    def test_partial_run_defaults_promote_false(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking", stop_after="raw")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued[0]["promote"] is False

    def test_explicit_promote_overrides_default_for_a_full_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking", promote=False)

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued[0]["promote"] is False

    def test_explicit_promote_overrides_default_for_a_partial_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking", stop_after="raw", promote=True)

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued[0]["promote"] is True


class TestProgression:
    def test_dispatches_only_the_ready_root_stage_first(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]
        assert queue.enqueued[0]["workflow_run_id"] == run_id
        assert store.active_workflow_runs()[0].status == "running"

    def test_does_not_redispatch_an_already_started_stage(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking")
        store.add_stage_run(run_id, "raw", status="running")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []

    def test_dispatches_next_stage_once_its_dependency_completes(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert len(queue.enqueued) == 1
        message = queue.enqueued[0]
        assert message["stage_name"] == "doubled"
        assert message["input_versions"] == {"raw": 1}
        assert message["promote"] is True

    def test_marks_run_completed_once_every_stage_is_done(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)
        store.add_stage_run(run_id, "doubled", status="completed", output_version=2)
        store.add_stage_run(run_id, "tripled", status="completed", output_version=3)

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert store.active_workflow_runs() == []

    def test_failed_stage_halts_progression_and_fails_the_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="failed", error="boom")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []

    def test_bad_dag_fails_the_run_immediately(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_workflow_run("feed_ranking")

        def broken_provider(workflow_name):
            raise ValueError("no workflow found")

        _poll(store, queue, broken_provider)

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []


class TestCancellation:
    def test_cancel_requested_marks_cancelled_and_dispatches_nothing(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking")
        store.request_cancel(run_id)

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []

    def test_cancelling_mid_run_stops_further_dispatch_but_keeps_completed_stages(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)
        store.request_cancel(run_id)

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []  # "doubled" never dispatched, even though "raw" is done
        assert store.active_workflow_runs() == []

    def test_a_run_with_no_cancel_requested_is_unaffected(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_workflow_run("feed_ranking")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]


class TestStartFrom:
    def test_skips_upstream_stages_and_seeds_from_input_versions(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_workflow_run(
            "feed_ranking", start_from="doubled", input_versions={"raw": 7}, promote=False
        )

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["doubled"]
        assert queue.enqueued[0]["input_versions"] == {"raw": 7}
        assert queue.enqueued[0]["promote"] is False

    def test_resume_run_continues_through_to_completion(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run(
            "feed_ranking", start_from="doubled", input_versions={"raw": 1}, promote=True, status="running"
        )
        store.add_stage_run(run_id, "doubled", status="completed", output_version=2)

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["tripled"]

    def test_missing_input_versions_for_start_from_deps_fails_the_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_workflow_run("feed_ranking", start_from="doubled", input_versions={})

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []

    def test_unknown_start_from_fails_the_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_workflow_run("feed_ranking", start_from="does_not_exist")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert store.active_workflow_runs() == []


class TestStopAfter:
    def test_halts_before_downstream_stages_dispatch(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking", stop_after="doubled", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)
        store.add_stage_run(run_id, "doubled", status="completed", output_version=2)

        _poll(store, queue, _registry_provider(_branching_registry()))

        assert queue.enqueued == []  # neither tripled nor quadrupled ever dispatched
        assert store.active_workflow_runs() == []  # run reached completed

    def test_unknown_stop_after_fails_the_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_workflow_run("feed_ranking", stop_after="does_not_exist")

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert store.active_workflow_runs() == []

    def test_not_reachable_from_start_from_fails_the_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        # "raw" is upstream of "doubled", not reachable from it
        store.add_workflow_run(
            "feed_ranking", start_from="doubled", stop_after="raw", input_versions={"raw": 1}
        )

        _poll(store, queue, _registry_provider(_linear_registry()))

        assert store.active_workflow_runs() == []


def _fallback_registry() -> StageRegistry:
    """Same shape as _linear_registry, but on_failure="fallback"."""
    registry = StageRegistry(on_failure="fallback")
    registry.stage("raw")(lambda: None)

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return raw * 2

    @registry.stage("tripled", depends_on=["doubled"])
    def tripled(doubled):
        return doubled * 3

    return registry


class TestFallback:
    def test_falls_back_to_current_version_and_continues(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        resources = InMemoryResourceClient()
        version = resources.upload_version("doubled", 99)
        resources.promote("doubled", version)

        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)
        store.add_stage_run(run_id, "doubled", status="failed", error="boom")

        poll_once(store, queue, _registry_provider(_fallback_registry()), resources)

        assert [m["stage_name"] for m in queue.enqueued] == ["tripled"]
        assert queue.enqueued[0]["input_versions"] == {"doubled": version}
        assert store.active_workflow_runs()[0].status == "running"

    def test_degrades_to_halt_when_no_fallback_version_exists(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        resources = InMemoryResourceClient()  # nothing ever promoted for "doubled"

        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)
        store.add_stage_run(run_id, "doubled", status="failed", error="boom")

        poll_once(store, queue, _registry_provider(_fallback_registry()), resources)

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []

    def test_halt_policy_registry_is_unaffected_by_a_resources_with_a_current_version(self):
        """Confirms on_failure="halt" (the default) never even looks at
        resource_store -- a fallback version being available doesn't change
        anything if the policy doesn't ask for it."""
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        resources = InMemoryResourceClient()
        version = resources.upload_version("doubled", 99)
        resources.promote("doubled", version)

        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)
        store.add_stage_run(run_id, "doubled", status="failed", error="boom")

        poll_once(store, queue, _registry_provider(_linear_registry()), resources)

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []


class TestInjectedRootDependency:
    def test_resolves_current_version_and_dispatches(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        resources = InMemoryResourceClient()
        version = resources.upload_version("raw", 5)
        resources.promote("raw", version)
        store.add_workflow_run("feed_ranking")

        poll_once(store, queue, _registry_provider(_registry_with_injected_root()), resources)

        assert [m["stage_name"] for m in queue.enqueued] == ["doubled"]
        assert queue.enqueued[0]["input_versions"] == {"raw": version}

    def test_fails_the_run_when_not_yet_injected(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        resources = InMemoryResourceClient()  # "raw" never uploaded
        store.add_workflow_run("feed_ranking")

        poll_once(store, queue, _registry_provider(_registry_with_injected_root()), resources)

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []
