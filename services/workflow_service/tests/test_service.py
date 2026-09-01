from datetime import datetime, timezone

import pytest

from errors import RunNotFoundError, ScheduleNotFoundError, StageRunNotFoundError, WorkflowNotFoundError
from memory import InMemoryScheduleRepository, InMemoryStageRunRepository, InMemoryWorkflowRunRepository
from models import RunStatus, ScheduleScope, StageRun, WorkflowRun
from service import WorkflowService

NOW = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def workflows_root(tmp_path):
    (tmp_path / "feed_ranking").mkdir()
    return tmp_path


@pytest.fixture
def schedules():
    return InMemoryScheduleRepository()


@pytest.fixture
def workflow_runs():
    return InMemoryWorkflowRunRepository()


@pytest.fixture
def stage_runs():
    return InMemoryStageRunRepository()


@pytest.fixture
def service(schedules, workflow_runs, stage_runs, workflows_root):
    return WorkflowService(schedules, workflow_runs, stage_runs, workflows_root)


def _seed_workflow_run(workflow_runs, *, id=1, status=RunStatus.REQUESTED, error=None):
    run = WorkflowRun(
        id=id,
        workflow_name="feed_ranking",
        status=status,
        requested_at=NOW,
        started_at=None,
        finished_at=None,
        error=error,
    )
    workflow_runs.add(run)
    return run


def _seed_stage_run(stage_runs, *, id=1, workflow_run_id=None, status=RunStatus.REQUESTED, error=None):
    stage_run = StageRun(
        id=id,
        workflow_run_id=workflow_run_id,
        workflow_name="feed_ranking",
        stage_name="score_items",
        input_versions={},
        promote=workflow_run_id is not None,
        output_version=None,
        status=status,
        requested_at=NOW,
        started_at=None,
        finished_at=None,
        error=error,
    )
    stage_runs.add(stage_run)
    return stage_run


class TestRequestRun:
    def test_creates_a_workflow_scoped_schedule(self, service):
        schedule = service.request_run("feed_ranking")

        assert schedule.workflow_name == "feed_ranking"
        assert schedule.scope == ScheduleScope.WORKFLOW
        assert schedule.stage_name is None
        assert schedule.dispatched_at is None

    def test_unknown_workflow_raises(self, service):
        with pytest.raises(WorkflowNotFoundError):
            service.request_run("does_not_exist")


class TestRequestStageRun:
    def test_creates_a_stage_scoped_schedule(self, service):
        schedule = service.request_stage_run(
            "feed_ranking", "score_items", input_versions={"aggregate_signals": 3}, promote=True
        )

        assert schedule.scope == ScheduleScope.STAGE
        assert schedule.stage_name == "score_items"
        assert schedule.input_versions == {"aggregate_signals": 3}
        assert schedule.promote is True
        assert schedule.dispatched_at is None

    def test_defaults_input_versions_and_promote(self, service):
        schedule = service.request_stage_run("feed_ranking", "score_items")

        assert schedule.input_versions == {}
        assert schedule.promote is False

    def test_unknown_workflow_raises(self, service):
        with pytest.raises(WorkflowNotFoundError):
            service.request_stage_run("does_not_exist", "score_items")


class TestGetScheduleStatus:
    def test_undispatched_schedule_is_requested(self, service):
        schedule = service.request_run("feed_ranking")

        status = service.get_schedule_status("feed_ranking", schedule.id)

        assert status.status == RunStatus.REQUESTED.value
        assert status.run_id is None
        assert status.stage_run_id is None

    def test_dispatched_workflow_schedule_proxies_run_status(self, service, schedules, workflow_runs):
        schedule = service.request_run("feed_ranking")
        run = _seed_workflow_run(workflow_runs, status=RunStatus.RUNNING)
        schedules.mark_dispatched(schedule.id, dispatched_at=NOW, run_id=run.id)

        status = service.get_schedule_status("feed_ranking", schedule.id)

        assert status.status == RunStatus.RUNNING.value
        assert status.run_id == run.id
        assert status.stage_run_id is None

    def test_dispatched_stage_schedule_proxies_stage_run_status(self, service, schedules, stage_runs):
        schedule = service.request_stage_run("feed_ranking", "score_items")
        stage_run = _seed_stage_run(stage_runs, status=RunStatus.FAILED, error="boom")
        schedules.mark_dispatched(schedule.id, dispatched_at=NOW, stage_run_id=stage_run.id)

        status = service.get_schedule_status("feed_ranking", schedule.id)

        assert status.status == RunStatus.FAILED.value
        assert status.error == "boom"
        assert status.stage_run_id == stage_run.id
        assert status.run_id is None

    def test_unknown_schedule_raises(self, service):
        with pytest.raises(ScheduleNotFoundError):
            service.get_schedule_status("feed_ranking", 999)


class TestGetRun:
    def test_returns_the_run(self, service, workflow_runs):
        seeded = _seed_workflow_run(workflow_runs)

        assert service.get_run("feed_ranking", seeded.id) == seeded

    def test_unknown_run_raises(self, service):
        with pytest.raises(RunNotFoundError):
            service.get_run("feed_ranking", 999)


class TestListStageRunsForRun:
    def test_lists_only_stage_runs_for_that_workflow_run(self, service, workflow_runs, stage_runs):
        run = _seed_workflow_run(workflow_runs)
        mine = _seed_stage_run(stage_runs, id=1, workflow_run_id=run.id)
        _seed_stage_run(stage_runs, id=2, workflow_run_id=None)  # standalone, unrelated

        assert service.list_stage_runs_for_run("feed_ranking", run.id) == [mine]

    def test_unknown_run_raises(self, service):
        with pytest.raises(RunNotFoundError):
            service.list_stage_runs_for_run("feed_ranking", 999)


class TestStageRunLifecycle:
    def test_start_marks_running(self, service, stage_runs):
        stage_run = _seed_stage_run(stage_runs)

        service.start_stage_run("feed_ranking", stage_run.id)

        updated = service.get_stage_run("feed_ranking", stage_run.id)
        assert updated.status == RunStatus.RUNNING
        assert updated.started_at is not None

    def test_complete_marks_completed_with_output_version(self, service, stage_runs):
        stage_run = _seed_stage_run(stage_runs)
        service.start_stage_run("feed_ranking", stage_run.id)

        service.complete_stage_run("feed_ranking", stage_run.id, output_version=5)

        updated = service.get_stage_run("feed_ranking", stage_run.id)
        assert updated.status == RunStatus.COMPLETED
        assert updated.output_version == 5

    def test_fail_marks_failed_with_error(self, service, stage_runs):
        stage_run = _seed_stage_run(stage_runs)
        service.start_stage_run("feed_ranking", stage_run.id)

        service.fail_stage_run("feed_ranking", stage_run.id, "boom")

        updated = service.get_stage_run("feed_ranking", stage_run.id)
        assert updated.status == RunStatus.FAILED
        assert updated.error == "boom"

    def test_unknown_stage_run_raises(self, service):
        with pytest.raises(StageRunNotFoundError):
            service.start_stage_run("feed_ranking", 999)
