from datetime import datetime, timezone

import pytest

from errors import RunNotFoundError, ScheduleNotFoundError, StageRunNotFoundError, WorkflowNotFoundError
from memory import InMemoryScheduleRepository, InMemoryStageRunRepository, InMemoryWorkflowRunRepository
from models import RunStatus, StageRun, WorkflowRun
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


def _seed_workflow_run(
    workflow_runs, *, id=1, start_from=None, stop_after=None, promote=True, status=RunStatus.REQUESTED, error=None
):
    run = WorkflowRun(
        id=id,
        workflow_name="feed_ranking",
        start_from=start_from,
        stop_after=stop_after,
        input_versions=None,
        promote=promote,
        status=status,
        requested_at=NOW,
        started_at=None,
        finished_at=None,
        error=error,
    )
    workflow_runs.add(run)
    return run


def _seed_stage_run(stage_runs, *, id=1, workflow_run_id=1, status=RunStatus.REQUESTED, error=None):
    stage_run = StageRun(
        id=id,
        workflow_run_id=workflow_run_id,
        workflow_name="feed_ranking",
        stage_name="score_items",
        input_versions={},
        promote=True,
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
    def test_full_run_has_no_start_from_or_stop_after(self, service):
        schedule = service.request_run("feed_ranking")

        assert schedule.workflow_name == "feed_ranking"
        assert schedule.start_from is None
        assert schedule.stop_after is None
        assert schedule.dispatched_at is None

    def test_single_stage_run_sets_start_from_and_stop_after_to_the_same_name(self, service):
        schedule = service.request_run(
            "feed_ranking",
            start_from="score_items",
            stop_after="score_items",
            input_versions={"aggregate_signals": 3},
            promote=True,
        )

        assert schedule.start_from == "score_items"
        assert schedule.stop_after == "score_items"
        assert schedule.input_versions == {"aggregate_signals": 3}
        assert schedule.promote is True

    def test_resume_run_sets_only_start_from(self, service):
        schedule = service.request_run("feed_ranking", start_from="score_items")

        assert schedule.start_from == "score_items"
        assert schedule.stop_after is None

    def test_promote_left_unset_is_passed_through_as_none(self, service):
        """workflow_service just persists whatever promote it's given --
        resolving the None-means-default-by-run-shape rule is the
        Scheduler's job, not this service's."""
        schedule = service.request_run("feed_ranking", start_from="score_items")

        assert schedule.promote is None

    def test_unknown_workflow_raises(self, service):
        with pytest.raises(WorkflowNotFoundError):
            service.request_run("does_not_exist")


class TestGetScheduleStatus:
    def test_undispatched_schedule_is_requested(self, service):
        schedule = service.request_run("feed_ranking")

        status = service.get_schedule_status("feed_ranking", schedule.id)

        assert status.status == RunStatus.REQUESTED.value
        assert status.run_id is None

    def test_dispatched_schedule_proxies_run_status(self, service, schedules, workflow_runs):
        schedule = service.request_run("feed_ranking")
        run = _seed_workflow_run(workflow_runs, status=RunStatus.RUNNING)
        schedules.mark_dispatched(schedule.id, dispatched_at=NOW, run_id=run.id)

        status = service.get_schedule_status("feed_ranking", schedule.id)

        assert status.status == RunStatus.RUNNING.value
        assert status.run_id == run.id

    def test_dispatched_schedule_proxies_failed_run_error(self, service, schedules, workflow_runs):
        schedule = service.request_run("feed_ranking")
        run = _seed_workflow_run(workflow_runs, status=RunStatus.FAILED, error="boom")
        schedules.mark_dispatched(schedule.id, dispatched_at=NOW, run_id=run.id)

        status = service.get_schedule_status("feed_ranking", schedule.id)

        assert status.status == RunStatus.FAILED.value
        assert status.error == "boom"

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
        run = _seed_workflow_run(workflow_runs, id=1)
        _seed_workflow_run(workflow_runs, id=2)
        mine = _seed_stage_run(stage_runs, id=1, workflow_run_id=1)
        _seed_stage_run(stage_runs, id=2, workflow_run_id=2)  # a different run, unrelated

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


class TestListWorkflows:
    def test_lists_directory_names_under_workflows_root(self, service, workflows_root):
        (workflows_root / "another_workflow").mkdir()

        assert service.list_workflows() == ["another_workflow", "feed_ranking"]

    def test_ignores_dotfiles_and_dunder_dirs(self, service, workflows_root):
        (workflows_root / "__pycache__").mkdir()
        (workflows_root / ".hidden").mkdir()

        assert service.list_workflows() == ["feed_ranking"]


class TestListRuns:
    def test_lists_only_runs_for_that_workflow_most_recent_first(self, service, workflow_runs, workflows_root):
        (workflows_root / "other").mkdir()
        _seed_workflow_run(workflow_runs, id=1)
        _seed_workflow_run(workflow_runs, id=2)
        other = WorkflowRun(
            id=3,
            workflow_name="other",
            start_from=None,
            stop_after=None,
            input_versions=None,
            promote=True,
            status=RunStatus.REQUESTED,
            requested_at=NOW,
            started_at=None,
            finished_at=None,
            error=None,
        )
        workflow_runs.add(other)

        runs = service.list_runs("feed_ranking")

        assert [r.id for r in runs] == [2, 1]

    def test_respects_limit(self, service, workflow_runs):
        _seed_workflow_run(workflow_runs, id=1)
        _seed_workflow_run(workflow_runs, id=2)

        assert [r.id for r in service.list_runs("feed_ranking", limit=1)] == [2]

    def test_unknown_workflow_raises(self, service):
        with pytest.raises(WorkflowNotFoundError):
            service.list_runs("does_not_exist")
