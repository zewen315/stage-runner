import pytest

from errors import RunNotFoundError, WorkflowNotFoundError
from memory import InMemoryRunQueue, InMemoryRunRepository
from models import RunStatus
from service import WorkflowService


@pytest.fixture
def workflows_root(tmp_path):
    (tmp_path / "feed_ranking").mkdir()
    return tmp_path


@pytest.fixture
def queue():
    return InMemoryRunQueue()


@pytest.fixture
def service(workflows_root, queue):
    return WorkflowService(InMemoryRunRepository(), queue, workflows_root)


class TestRequestRun:
    def test_creates_a_requested_run(self, service):
        run = service.request_run("feed_ranking")

        assert run.workflow_name == "feed_ranking"
        assert run.status == RunStatus.REQUESTED
        assert run.started_at is None

    def test_enqueues_the_run(self, service, queue):
        run = service.request_run("feed_ranking")

        assert queue.enqueued == [(run.id, "feed_ranking")]

    def test_unknown_workflow_raises(self, service):
        with pytest.raises(WorkflowNotFoundError):
            service.request_run("does_not_exist")


class TestGetRun:
    def test_returns_the_run(self, service):
        created = service.request_run("feed_ranking")
        fetched = service.get_run("feed_ranking", created.id)

        assert fetched == created

    def test_unknown_run_raises(self, service):
        with pytest.raises(RunNotFoundError):
            service.get_run("feed_ranking", 999)


class TestRunLifecycle:
    def test_start_marks_running(self, service):
        run = service.request_run("feed_ranking")

        service.start_run("feed_ranking", run.id)

        updated = service.get_run("feed_ranking", run.id)
        assert updated.status == RunStatus.RUNNING
        assert updated.started_at is not None

    def test_complete_marks_completed(self, service):
        run = service.request_run("feed_ranking")
        service.start_run("feed_ranking", run.id)

        service.complete_run("feed_ranking", run.id)

        updated = service.get_run("feed_ranking", run.id)
        assert updated.status == RunStatus.COMPLETED
        assert updated.finished_at is not None

    def test_fail_marks_failed_with_error(self, service):
        run = service.request_run("feed_ranking")
        service.start_run("feed_ranking", run.id)

        service.fail_run("feed_ranking", run.id, "aggregate_signals: boom")

        updated = service.get_run("feed_ranking", run.id)
        assert updated.status == RunStatus.FAILED
        assert updated.error == "aggregate_signals: boom"
