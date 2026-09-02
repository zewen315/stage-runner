"""Shared fixtures for the system test suite: everything here talks real
HTTP to a real, already-running `docker compose up` stack -- no fakes, no
mocked repositories, no in-process app. If the stack isn't reachable, the
whole session skips with a message telling you how to start it, rather
than every test failing with a confusing connection error.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

BASE_URL = "http://localhost:8080"
RAW_EVENTS_PATH = Path(__file__).resolve().parents[1] / "seed_data" / "raw_events.json"


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        try:
            client.get("/workflows").raise_for_status()
        except httpx.HTTPError as exc:
            pytest.skip(
                f"Stage Runner isn't reachable at {BASE_URL} ({exc}) -- "
                "start it first: `docker compose up --build -d`"
            )
        yield client


@pytest.fixture(scope="session")
def raw_events_current(client):
    """Every workflow here starts from raw_events -- upload+promote a
    fresh version once per session so a run always has something to
    consume, the same way the README's quickstart does by hand."""
    value = json.loads(RAW_EVENTS_PATH.read_text())
    response = client.post("/resources/raw_events/versions", json={"value": value, "is_test": False})
    response.raise_for_status()
    version = response.json()["version"]
    client.post("/resources/raw_events/promotions", json={"version": version}).raise_for_status()
    return version


@pytest.fixture(scope="session")
def completed_feed_success_run(client, raw_events_current):
    """A full, promoted feed_success run -- shared across every test that
    either checks the happy path itself or just needs a promoted
    score_items to already exist (e.g. to fall back to), so it only runs
    once per session instead of once per test."""
    return trigger_and_wait(client, "feed_success", {"promote": True})


def wait_for_schedule_terminal(client: httpx.Client, workflow: str, schedule_id: int, timeout: float = 120) -> dict:
    """Polls a schedule (the same way the CLI's `run` command does) until
    its dispatched run reaches a terminal status; returns the final
    schedule status body."""
    deadline = time.monotonic() + timeout
    while True:
        status = client.get(f"/workflows/{workflow}/schedules/{schedule_id}").json()
        if status["status"] not in ("requested", "running"):
            return status
        if time.monotonic() > deadline:
            pytest.fail(f"schedule {schedule_id} for {workflow!r} did not finish within {timeout}s: {status}")
        time.sleep(1)


def wait_for_dispatch(client: httpx.Client, workflow: str, schedule_id: int, timeout: float = 30) -> int:
    """Polls until a schedule has been dispatched to a WorkflowRun,
    returning that run's id -- for tests that need to act on the run
    (e.g. cancel it) before it necessarily finishes."""
    deadline = time.monotonic() + timeout
    while True:
        status = client.get(f"/workflows/{workflow}/schedules/{schedule_id}").json()
        if status["run_id"] is not None:
            return status["run_id"]
        if time.monotonic() > deadline:
            pytest.fail(f"schedule {schedule_id} for {workflow!r} was not dispatched within {timeout}s")
        time.sleep(0.5)


def trigger_and_wait(client: httpx.Client, workflow: str, body: dict, timeout: float = 120) -> dict:
    """Triggers a run and polls it to completion -- the system-test
    equivalent of `stagerunner run <workflow>`. Returns the final
    schedule status body (id, run_id, status, error)."""
    schedule = client.post(f"/workflows/{workflow}/runs", json=body)
    schedule.raise_for_status()
    return wait_for_schedule_terminal(client, workflow, schedule.json()["id"], timeout=timeout)
