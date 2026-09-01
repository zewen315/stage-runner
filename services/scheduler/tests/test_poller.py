from stages import StageRegistry

from memory import InMemoryRunQueue, InMemoryScheduleStore
from poller import poll_once


def _linear_registry() -> StageRegistry:
    """raw -> doubled -> tripled, a simple two-hop chain."""
    registry = StageRegistry()
    registry.import_stage("raw", path="raw.json")

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return raw * 2

    @registry.stage("tripled", depends_on=["doubled"])
    def tripled(doubled):
        return doubled * 3

    return registry


def _registry_provider(registry: StageRegistry):
    return lambda workflow_name: registry


class TestIntakeStandalone:
    def test_stage_scoped_schedule_dispatches_immediately_without_a_workflow_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule(
            "feed_ranking", "stage", stage_name="score_items",
            input_versions={"aggregate_signals": 3}, promote=True,
        )

        poll_once(store, queue, _registry_provider(_linear_registry()))

        assert len(queue.enqueued) == 1
        message = queue.enqueued[0]
        assert message["workflow_run_id"] is None
        assert message["stage_name"] == "score_items"
        assert message["input_versions"] == {"aggregate_signals": 3}
        assert message["promote"] is True
        assert store.active_workflow_runs() == []

    def test_stage_scoped_schedule_defaults_input_versions_and_promote(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking", "stage", stage_name="raw")

        poll_once(store, queue, _registry_provider(_linear_registry()))

        message = queue.enqueued[0]
        assert message["input_versions"] == {}
        assert message["promote"] is False


class TestIntakeWorkflow:
    def test_workflow_scoped_schedule_creates_a_run_not_a_queue_message(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_schedule("feed_ranking", "workflow")

        poll_once(store, queue, _registry_provider(_linear_registry()))

        # a WorkflowRun row exists, but nothing about *it* is ever queued --
        # only its ready root stage gets dispatched, by the same tick's
        # progression pass (covered in detail by TestProgression)
        assert len(store.active_workflow_runs()) == 1
        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]
        assert queue.enqueued[0]["workflow_run_id"] == store.active_workflow_runs()[0].id


class TestProgression:
    def test_dispatches_only_the_ready_root_stage_first(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking")

        poll_once(store, queue, _registry_provider(_linear_registry()))

        assert [m["stage_name"] for m in queue.enqueued] == ["raw"]
        assert queue.enqueued[0]["workflow_run_id"] == run_id
        assert store.active_workflow_runs()[0].status == "running"

    def test_does_not_redispatch_an_already_started_stage(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking")
        store.add_stage_run(run_id, "raw", status="running")

        poll_once(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []

    def test_dispatches_next_stage_once_its_dependency_completes(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="completed", output_version=1)

        poll_once(store, queue, _registry_provider(_linear_registry()))

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

        poll_once(store, queue, _registry_provider(_linear_registry()))

        assert store.active_workflow_runs() == []

    def test_failed_stage_halts_progression_and_fails_the_run(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        run_id = store.add_workflow_run("feed_ranking", status="running")
        store.add_stage_run(run_id, "raw", status="failed", error="boom")

        poll_once(store, queue, _registry_provider(_linear_registry()))

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []

    def test_bad_dag_fails_the_run_immediately(self):
        store = InMemoryScheduleStore()
        queue = InMemoryRunQueue()
        store.add_workflow_run("feed_ranking")

        def broken_provider(workflow_name):
            raise ValueError("no workflow found")

        poll_once(store, queue, broken_provider)

        assert queue.enqueued == []
        assert store.active_workflow_runs() == []
