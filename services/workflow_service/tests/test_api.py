"""Deliberately narrow: business logic is already covered in test_service.py.
This checks the HTTP contract -- status codes and that routes call the
right service methods -- not the full behavior matrix again.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api import app, get_service
from memory import InMemoryScheduleRepository, InMemoryStageRunRepository, InMemoryWorkflowRunRepository
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
def client(tmp_path, schedules, workflow_runs, stage_runs):
    (tmp_path / "feed_ranking").mkdir()
    service = WorkflowService(schedules, workflow_runs, stage_runs, tmp_path)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_request_run_returns_202_with_requested_status(client):
    response = client.post("/workflows/feed_ranking/runs")

    assert response.status_code == 202
    body = response.json()
    assert body["workflow_name"] == "feed_ranking"
    assert body["scope"] == "workflow"
    assert body["status"] == "requested"


def test_request_run_unknown_workflow_is_404(client):
    response = client.post("/workflows/does_not_exist/runs")
    assert response.status_code == 404


def test_request_stage_run_returns_202(client):
    response = client.post(
        "/workflows/feed_ranking/stages/score_items/runs",
        json={"input_versions": {"aggregate_signals": 2}, "promote": True},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["scope"] == "stage"
    assert body["stage_name"] == "score_items"
    assert body["status"] == "requested"


def test_get_schedule_status_proxies_dispatched_run(client, schedules, workflow_runs):
    schedule = client.post("/workflows/feed_ranking/runs").json()
    workflow_runs.add(
        WorkflowRun(
            id=42,
            workflow_name="feed_ranking",
            status=RunStatus.RUNNING,
            requested_at=NOW,
            started_at=NOW,
            finished_at=None,
            error=None,
        )
    )
    schedules.mark_dispatched(schedule["id"], dispatched_at=NOW, run_id=42)

    response = client.get(f"/workflows/feed_ranking/schedules/{schedule['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["run_id"] == 42


def test_get_schedule_status_unknown_is_404(client):
    response = client.get("/workflows/feed_ranking/schedules/999")
    assert response.status_code == 404


def test_get_run(client, workflow_runs):
    workflow_runs.add(
        WorkflowRun(
            id=1,
            workflow_name="feed_ranking",
            status=RunStatus.COMPLETED,
            requested_at=NOW,
            started_at=NOW,
            finished_at=NOW,
            error=None,
        )
    )

    response = client.get("/workflows/feed_ranking/runs/1")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_get_run_unknown_is_404(client):
    response = client.get("/workflows/feed_ranking/runs/999")
    assert response.status_code == 404


def test_list_stage_runs_for_run(client, workflow_runs, stage_runs):
    workflow_runs.add(
        WorkflowRun(
            id=1,
            workflow_name="feed_ranking",
            status=RunStatus.RUNNING,
            requested_at=NOW,
            started_at=NOW,
            finished_at=None,
            error=None,
        )
    )
    stage_runs.add(
        StageRun(
            id=7,
            workflow_run_id=1,
            workflow_name="feed_ranking",
            stage_name="raw_events",
            input_versions={},
            promote=True,
            output_version=None,
            status=RunStatus.RUNNING,
            requested_at=NOW,
            started_at=NOW,
            finished_at=None,
            error=None,
        )
    )

    response = client.get("/workflows/feed_ranking/runs/1/stage-runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == 7


def test_full_stage_run_lifecycle_via_worker_endpoints(client, stage_runs):
    stage_runs.add(
        StageRun(
            id=1,
            workflow_run_id=None,
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
    )

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
    stage_runs.add(
        StageRun(
            id=1,
            workflow_run_id=None,
            workflow_name="feed_ranking",
            stage_name="score_items",
            input_versions={},
            promote=False,
            output_version=None,
            status=RunStatus.RUNNING,
            requested_at=NOW,
            started_at=NOW,
            finished_at=None,
            error=None,
        )
    )

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
