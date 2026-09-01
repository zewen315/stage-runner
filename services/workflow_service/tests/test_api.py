"""Deliberately narrow: business logic is already covered in test_service.py.
This checks the HTTP contract -- status codes and that routes call the
right service methods -- not the full behavior matrix again.
"""

import pytest
from fastapi.testclient import TestClient

from api import app, get_service
from memory import InMemoryRunQueue, InMemoryRunRepository
from service import WorkflowService


@pytest.fixture
def client(tmp_path):
    (tmp_path / "feed_ranking").mkdir()
    service = WorkflowService(InMemoryRunRepository(), InMemoryRunQueue(), tmp_path)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_request_run_returns_202_with_requested_status(client):
    response = client.post("/workflows/feed_ranking/runs")

    assert response.status_code == 202
    body = response.json()
    assert body["workflow_name"] == "feed_ranking"
    assert body["status"] == "requested"


def test_unknown_workflow_is_404(client):
    response = client.post("/workflows/does_not_exist/runs")
    assert response.status_code == 404


def test_full_lifecycle_via_worker_endpoints(client):
    run = client.post("/workflows/feed_ranking/runs").json()

    assert client.post(f"/workflows/feed_ranking/runs/{run['id']}/start").status_code == 204
    assert client.get(f"/workflows/feed_ranking/runs/{run['id']}").json()["status"] == "running"

    assert client.post(f"/workflows/feed_ranking/runs/{run['id']}/complete").status_code == 204
    assert client.get(f"/workflows/feed_ranking/runs/{run['id']}").json()["status"] == "completed"


def test_fail_run_records_error(client):
    run = client.post("/workflows/feed_ranking/runs").json()
    client.post(f"/workflows/feed_ranking/runs/{run['id']}/start")

    response = client.post(
        f"/workflows/feed_ranking/runs/{run['id']}/fail", json={"error": "boom"}
    )
    assert response.status_code == 204

    updated = client.get(f"/workflows/feed_ranking/runs/{run['id']}").json()
    assert updated["status"] == "failed"
    assert updated["error"] == "boom"


def test_unknown_run_is_404(client):
    response = client.get("/workflows/feed_ranking/runs/999")
    assert response.status_code == 404


def test_healthz():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
