"""Deliberately narrow: business logic is already covered in test_service.py.
This checks the HTTP contract -- status codes and that routes call the
right service methods -- not the full behavior matrix again.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api import app, get_service
from memory import (
    InMemoryRecurringScheduleRepository,
    InMemoryScheduleRepository,
    InMemoryStageRunRepository,
    InMemoryWorkflowRunRepository,
)
from models import RunStatus, StageRun, WorkflowRun
from service import WorkflowService

NOW = datetime.now(timezone.utc).isoformat()


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
def recurring_schedules():
    return InMemoryRecurringScheduleRepository()


@pytest.fixture
def client(tmp_path, schedules, workflow_runs, stage_runs, recurring_schedules):
    (tmp_path / "feed_ranking").mkdir()
    service = WorkflowService(schedules, workflow_runs, stage_runs, tmp_path, recurring_schedules)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def _workflow_run(**overrides):
    defaults = dict(
        id=1,
        workflow_name="feed_ranking",
        start_from=None,
        stop_after=None,
        input_versions=None,
        promote=True,
        status=RunStatus.RUNNING,
        requested_at=NOW,
        started_at=NOW,
        finished_at=None,
        error=None,
    )
    return WorkflowRun(**{**defaults, **overrides})


def _stage_run(**overrides):
    defaults = dict(
        id=1,
        workflow_run_id=1,
        workflow_name="feed_ranking",
        stage_name="score_items",
        input_versions={},
        promote=False,
        output_version=None,
        status=RunStatus.REQUESTED,
        requested_at=NOW,
        started_at=None,
        finished_at=None,
        error=None,
    )
    return StageRun(**{**defaults, **overrides})


def test_request_run_returns_202_with_requested_status(client):
    response = client.post("/workflows/feed_ranking/runs")

    assert response.status_code == 202
    body = response.json()
    assert body["workflow_name"] == "feed_ranking"
    assert body["start_from"] is None
    assert body["stop_after"] is None
    assert body["status"] == "requested"


def test_request_run_unknown_workflow_is_404(client):
    response = client.post("/workflows/does_not_exist/runs")
    assert response.status_code == 404


def test_request_run_with_start_from_and_stop_after_returns_202(client):
    response = client.post(
        "/workflows/feed_ranking/runs",
        json={
            "start_from": "score_items",
            "stop_after": "score_items",
            "input_versions": {"aggregate_signals": 2},
            "promote": True,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["start_from"] == "score_items"
    assert body["stop_after"] == "score_items"
    assert body["status"] == "requested"


def test_request_run_with_run_at_returns_202(client):
    response = client.post(
        "/workflows/feed_ranking/runs", json={"run_at": "2099-01-01T00:00:00+00:00"}
    )

    assert response.status_code == 202
    assert response.json()["run_at"] == "2099-01-01T00:00:00+00:00"


def test_get_schedule_status_proxies_dispatched_run(client, schedules, workflow_runs):
    schedule = client.post("/workflows/feed_ranking/runs").json()
    workflow_runs.add(_workflow_run(id=42, status=RunStatus.RUNNING))
    schedules.mark_dispatched(schedule["id"], dispatched_at=NOW, run_id=42)

    response = client.get(f"/workflows/feed_ranking/schedules/{schedule['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["run_id"] == 42


def test_get_schedule_status_unknown_is_404(client):
    response = client.get("/workflows/feed_ranking/schedules/999")
    assert response.status_code == 404


def test_list_pending_schedules(client):
    client.post("/workflows/feed_ranking/runs")

    response = client.get("/workflows/feed_ranking/schedules")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "requested"


def test_list_pending_schedules_unknown_workflow_is_404(client):
    response = client.get("/workflows/does_not_exist/schedules")
    assert response.status_code == 404


def test_create_recurring_schedule_returns_201(client):
    response = client.post(
        "/workflows/feed_ranking/recurring-schedules", json={"cron_expression": "* * * * *"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["cron_expression"] == "* * * * *"
    assert body["enabled"] is True


def test_create_recurring_schedule_invalid_cron_is_400(client):
    response = client.post(
        "/workflows/feed_ranking/recurring-schedules", json={"cron_expression": "not a cron"}
    )
    assert response.status_code == 400


def test_list_recurring_schedules(client):
    client.post("/workflows/feed_ranking/recurring-schedules", json={"cron_expression": "* * * * *"})

    response = client.get("/workflows/feed_ranking/recurring-schedules")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_cancel_recurring_schedule(client):
    created = client.post(
        "/workflows/feed_ranking/recurring-schedules", json={"cron_expression": "* * * * *"}
    ).json()

    response = client.post(f"/workflows/feed_ranking/recurring-schedules/{created['id']}/cancel")
    assert response.status_code == 204

    [recurring] = client.get("/workflows/feed_ranking/recurring-schedules").json()
    assert recurring["enabled"] is False


def test_cancel_recurring_schedule_unknown_is_404(client):
    response = client.post("/workflows/feed_ranking/recurring-schedules/999/cancel")
    assert response.status_code == 404


def test_get_run(client, workflow_runs):
    workflow_runs.add(_workflow_run(id=1, status=RunStatus.COMPLETED, finished_at=NOW))

    response = client.get("/workflows/feed_ranking/runs/1")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_get_run_unknown_is_404(client):
    response = client.get("/workflows/feed_ranking/runs/999")
    assert response.status_code == 404


def test_list_workflows(client):
    response = client.get("/workflows")

    assert response.status_code == 200
    assert response.json() == ["feed_ranking"]


def test_list_stages(client, tmp_path):
    workflow_dir = tmp_path / "api_stage_list"
    workflow_dir.mkdir()
    (workflow_dir / "__init__.py").write_text(
        """
from stages import StageRegistry

registry = StageRegistry()


@registry.stage("raw", depends_on=[])
def raw():
    return {"n": 1}
"""
    )

    response = client.get("/workflows/api_stage_list/stages")

    assert response.status_code == 200
    assert response.json() == [{"name": "raw", "depends_on": []}]


def test_list_stages_unknown_workflow_is_404(client):
    response = client.get("/workflows/does_not_exist/stages")
    assert response.status_code == 404


def test_list_runs_most_recent_first(client, workflow_runs):
    workflow_runs.add(_workflow_run(id=1))
    workflow_runs.add(_workflow_run(id=2))

    response = client.get("/workflows/feed_ranking/runs")

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [2, 1]


def test_list_runs_unknown_workflow_is_404(client):
    response = client.get("/workflows/does_not_exist/runs")
    assert response.status_code == 404


def test_list_stage_runs_for_run(client, workflow_runs, stage_runs):
    workflow_runs.add(_workflow_run(id=1))
    stage_runs.add(_stage_run(id=7, workflow_run_id=1, stage_name="raw_events", status=RunStatus.RUNNING))

    response = client.get("/workflows/feed_ranking/runs/1/stage-runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == 7


def test_full_stage_run_lifecycle_via_worker_endpoints(client, stage_runs):
    stage_runs.add(_stage_run(id=1))

    assert client.post("/workflows/feed_ranking/stage-runs/1/start").status_code == 204
    assert client.get("/workflows/feed_ranking/stage-runs/1").json()["status"] == "running"

    response = client.post(
        "/workflows/feed_ranking/stage-runs/1/complete", json={"output_version": 3}
    )
    assert response.status_code == 204

    updated = client.get("/workflows/feed_ranking/stage-runs/1").json()
    assert updated["status"] == "completed"
    assert updated["output_version"] == 3


def test_fail_stage_run_records_error(client, stage_runs):
    stage_runs.add(_stage_run(id=1, status=RunStatus.RUNNING))

    response = client.post("/workflows/feed_ranking/stage-runs/1/fail", json={"error": "boom"})
    assert response.status_code == 204

    updated = client.get("/workflows/feed_ranking/stage-runs/1").json()
    assert updated["status"] == "failed"
    assert updated["error"] == "boom"


def test_get_stage_run_unknown_is_404(client):
    response = client.get("/workflows/feed_ranking/stage-runs/999")
    assert response.status_code == 404


def test_healthz():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
