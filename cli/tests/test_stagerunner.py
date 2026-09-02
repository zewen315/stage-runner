"""Tests the CLI's own logic in isolation: argument parsing/validation and
the request bodies it builds from flags -- never a real network call.
`httpx.Client` is monkeypatched to a FakeClient that records every call
and lets each test script its own canned responses, so these run with no
server, no Docker, in milliseconds.
"""

from __future__ import annotations

import argparse
import json

import httpx
import pytest

import stagerunner


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


class FakeClient:
    """Stands in for httpx.Client: records every (method, path, json) call
    and answers via a test-supplied `respond` callback, which can inspect
    the call count to script a sequence (e.g. a poll loop's
    requested -> running -> completed)."""

    def __init__(self, base_url="", respond=None):
        self.base_url = base_url
        self.calls = []
        self._respond = respond or (lambda method, path, json_body: FakeResponse(200, {}))

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        return self._respond("POST", path, json)

    def get(self, path):
        self.calls.append(("GET", path, None))
        return self._respond("GET", path, None)


@pytest.fixture
def fake_client(monkeypatch):
    """Installs a FakeClient with a default 200/{} responder; a test can
    read `.calls` afterward, or pass its own `respond` via
    `install(respond=...)` before invoking the CLI."""
    holder = {}

    def install(respond=None):
        client = FakeClient(respond=respond)
        holder["client"] = client
        monkeypatch.setattr(httpx, "Client", lambda base_url="": client)
        return client

    install()  # default, so tests that don't care can just use fake_client.calls
    monkeypatch.setattr(stagerunner.time, "sleep", lambda seconds: None)
    yield type("Fixture", (), {"install": staticmethod(install), "client": property(lambda self: holder["client"])})()


class TestParseInput:
    def test_parses_resource_equals_version(self):
        assert stagerunner._parse_input("score_items=3") == ("score_items", 3)

    def test_missing_equals_raises(self):
        with pytest.raises(argparse.ArgumentTypeError):
            stagerunner._parse_input("score_items")

    def test_non_integer_version_raises(self):
        with pytest.raises(ValueError):
            stagerunner._parse_input("score_items=abc")


class TestParseAt:
    def test_naive_timestamp_gets_utc(self):
        result = stagerunner._parse_at("2099-01-01T00:00:00")
        assert result == "2099-01-01T00:00:00+00:00"

    def test_tz_aware_timestamp_preserved(self):
        result = stagerunner._parse_at("2099-01-01T00:00:00-05:00")
        assert result == "2099-01-01T00:00:00-05:00"

    def test_invalid_timestamp_raises(self):
        with pytest.raises(argparse.ArgumentTypeError):
            stagerunner._parse_at("not a timestamp")


class TestRunArgValidation:
    def test_stage_with_start_from_exits_nonzero(self, fake_client, capsys):
        with pytest.raises(SystemExit) as exc:
            stagerunner.main(["run", "feed_success", "--stage", "score_items", "--start-from", "score_items"])
        assert exc.value.code != 0

    def test_stage_with_stop_after_exits_nonzero(self, fake_client, capsys):
        with pytest.raises(SystemExit) as exc:
            stagerunner.main(["run", "feed_success", "--stage", "score_items", "--stop-after", "rank_feed"])
        assert exc.value.code != 0


class TestRunBody:
    def _respond_completed(self, method, path, json_body):
        if method == "POST":
            return FakeResponse(200, {"id": 1})
        return FakeResponse(200, {"id": 1, "status": "completed", "run_id": 42, "error": None})

    def test_plain_run_sends_empty_body(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        stagerunner.main(["run", "feed_success"])
        method, path, body = fake_client.client.calls[0]
        assert (method, path) == ("POST", "/workflows/feed_success/runs")
        assert body == {}

    def test_stage_sugar_sets_start_from_and_stop_after(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        stagerunner.main(["run", "feed_success", "--stage", "score_items"])
        _, _, body = fake_client.client.calls[0]
        assert body["start_from"] == "score_items"
        assert body["stop_after"] == "score_items"

    def test_start_from_alone_omits_stop_after(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        stagerunner.main(["run", "feed_success", "--start-from", "score_items"])
        _, _, body = fake_client.client.calls[0]
        assert body["start_from"] == "score_items"
        assert "stop_after" not in body

    def test_promote_flag_included_only_when_set(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        stagerunner.main(["run", "feed_success", "--promote"])
        _, _, body = fake_client.client.calls[0]
        assert body["promote"] is True

    def test_no_promote_flag_omits_it(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        stagerunner.main(["run", "feed_success"])
        _, _, body = fake_client.client.calls[0]
        assert "promote" not in body

    def test_input_versions_repeatable(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        stagerunner.main(
            ["run", "feed_success", "--start-from", "rank_feed", "--input", "score_items=3", "--input", "raw=1"]
        )
        _, _, body = fake_client.client.calls[0]
        assert body["input_versions"] == {"score_items": 3, "raw": 1}

    def test_on_failure_included_when_set(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        stagerunner.main(["run", "feed_success", "--on-failure", "fallback"])
        _, _, body = fake_client.client.calls[0]
        assert body["on_failure"] == "fallback"

    def test_at_sets_run_at_and_implies_no_wait(self, fake_client):
        fake_client.install(respond=self._respond_completed)
        exit_code = stagerunner.main(["run", "feed_success", "--at", "2099-01-01T00:00:00"])
        _, _, body = fake_client.client.calls[0]
        assert body["run_at"] == "2099-01-01T00:00:00+00:00"
        # --at implies --no-wait: only the initial POST + one status GET, no poll loop
        assert len(fake_client.client.calls) == 2
        assert exit_code == 0

    def test_unknown_workflow_is_404_returns_1(self, fake_client, capsys):
        fake_client.install(respond=lambda m, p, j: FakeResponse(404))
        exit_code = stagerunner.main(["run", "does_not_exist"])
        assert exit_code == 1
        assert "no workflow" in capsys.readouterr().err

    def test_invalid_on_failure_is_400_returns_1(self, fake_client, capsys):
        fake_client.install(respond=lambda m, p, j: FakeResponse(400, {"detail": "bad on_failure"}))
        exit_code = stagerunner.main(["run", "feed_success", "--on-failure", "fallback"])
        assert exit_code == 1
        assert "bad on_failure" in capsys.readouterr().err


class TestPollSchedule:
    def test_no_wait_returns_after_one_status_check(self, fake_client):
        fake_client.install(
            respond=lambda m, p, j: FakeResponse(200, {"id": 1, "status": "requested", "run_id": None})
        )
        exit_code = stagerunner.main(["run", "feed_success", "--no-wait"])
        assert exit_code == 0
        # POST to create + one GET for status, no polling loop
        assert len(fake_client.client.calls) == 2

    def test_waits_through_running_to_completed(self, fake_client):
        statuses = iter(["requested", "running", "running", "completed"])

        def respond(method, path, json_body):
            if method == "POST":
                return FakeResponse(200, {"id": 1})
            return FakeResponse(200, {"id": 1, "status": next(statuses), "run_id": 42, "error": None})

        fake_client.install(respond=respond)
        exit_code = stagerunner.main(["run", "feed_success"])
        assert exit_code == 0

    def test_failed_run_returns_1_and_prints_error(self, fake_client, capsys):
        def respond(method, path, json_body):
            if method == "POST":
                return FakeResponse(200, {"id": 1})
            return FakeResponse(200, {"id": 1, "status": "failed", "run_id": 42, "error": "boom"})

        fake_client.install(respond=respond)
        exit_code = stagerunner.main(["run", "feed_success"])
        assert exit_code == 1
        assert "boom" in capsys.readouterr().err


class TestResourceUpload:
    def test_uploads_and_promotes_by_default(self, fake_client, tmp_path, capsys):
        f = tmp_path / "raw_events.json"
        f.write_text(json.dumps([{"item_id": "post_1", "event": "impression"}]))

        calls_seen = []

        def respond(method, path, json_body):
            calls_seen.append((method, path, json_body))
            if path.endswith("/versions"):
                return FakeResponse(200, {"version": 3})
            return FakeResponse(200, {})

        fake_client.install(respond=respond)
        exit_code = stagerunner.main(["resource", "upload", "raw_events", str(f)])

        assert exit_code == 0
        upload_call = calls_seen[0]
        assert upload_call[1] == "/resources/raw_events/versions"
        assert upload_call[2]["is_test"] is False
        promote_call = calls_seen[1]
        assert promote_call[1] == "/resources/raw_events/promotions"
        assert promote_call[2] == {"version": 3}
        assert "current" in capsys.readouterr().out

    def test_no_promote_skips_promotion_call(self, fake_client, tmp_path):
        f = tmp_path / "raw_events.json"
        f.write_text(json.dumps([]))

        fake_client.install(respond=lambda m, p, j: FakeResponse(200, {"version": 1}))
        stagerunner.main(["resource", "upload", "raw_events", str(f), "--no-promote"])

        assert len(fake_client.client.calls) == 1  # upload only, no promotion POST
        _, _, body = fake_client.client.calls[0]
        assert body["is_test"] is True

    def test_validation_failure_is_400_returns_1(self, fake_client, tmp_path, capsys):
        f = tmp_path / "raw_events.json"
        f.write_text(json.dumps({"not": "a list"}))

        fake_client.install(respond=lambda m, p, j: FakeResponse(400, {"detail": "raw_events must be a list"}))
        exit_code = stagerunner.main(["resource", "upload", "raw_events", str(f)])

        assert exit_code == 1
        assert "raw_events must be a list" in capsys.readouterr().err


class TestRecurringCreate:
    def test_cron_sets_cron_expression(self, fake_client):
        fake_client.install(respond=lambda m, p, j: FakeResponse(200, {"id": 1, "next_run_at": "later"}))
        stagerunner.main(["recurring", "create", "feed_success", "--cron", "0 * * * *"])
        _, _, body = fake_client.client.calls[0]
        assert body["cron_expression"] == "0 * * * *"
        assert "interval_seconds" not in body

    def test_interval_seconds_sets_interval(self, fake_client):
        fake_client.install(respond=lambda m, p, j: FakeResponse(200, {"id": 1, "next_run_at": "later"}))
        stagerunner.main(["recurring", "create", "feed_success", "--interval-seconds", "30"])
        _, _, body = fake_client.client.calls[0]
        assert body["interval_seconds"] == 30
        assert "cron_expression" not in body

    def test_cron_and_interval_seconds_mutually_exclusive(self, fake_client):
        with pytest.raises(SystemExit) as exc:
            stagerunner.main(
                ["recurring", "create", "feed_success", "--cron", "* * * * *", "--interval-seconds", "30"]
            )
        assert exc.value.code != 0

    def test_neither_cron_nor_interval_required(self, fake_client):
        with pytest.raises(SystemExit) as exc:
            stagerunner.main(["recurring", "create", "feed_success"])
        assert exc.value.code != 0

    def test_stage_with_start_from_exits_nonzero(self, fake_client):
        with pytest.raises(SystemExit) as exc:
            stagerunner.main(
                [
                    "recurring",
                    "create",
                    "feed_success",
                    "--cron",
                    "* * * * *",
                    "--stage",
                    "score_items",
                    "--start-from",
                    "score_items",
                ]
            )
        assert exc.value.code != 0

    def test_invalid_recurrence_is_400_returns_1(self, fake_client, capsys):
        fake_client.install(respond=lambda m, p, j: FakeResponse(400, {"detail": "bad recurrence"}))
        exit_code = stagerunner.main(["recurring", "create", "feed_success", "--interval-seconds", "0"])
        assert exit_code == 1
        assert "bad recurrence" in capsys.readouterr().err


class TestRecurringList:
    def test_prints_cron_cadence(self, fake_client, capsys):
        fake_client.install(
            respond=lambda m, p, j: FakeResponse(
                200,
                [
                    {
                        "id": 1,
                        "cron_expression": "0 * * * *",
                        "interval_seconds": None,
                        "enabled": True,
                        "next_run_at": "2099-01-01T00:00:00+00:00",
                    }
                ],
            )
        )
        stagerunner.main(["recurring", "list", "feed_success"])
        out = capsys.readouterr().out
        assert "0 * * * *" in out
        assert "enabled" in out

    def test_prints_interval_cadence_for_cancelled_schedule(self, fake_client, capsys):
        fake_client.install(
            respond=lambda m, p, j: FakeResponse(
                200,
                [
                    {
                        "id": 2,
                        "cron_expression": None,
                        "interval_seconds": 30,
                        "enabled": False,
                        "next_run_at": "2099-01-01T00:00:00+00:00",
                    }
                ],
            )
        )
        stagerunner.main(["recurring", "list", "feed_success"])
        out = capsys.readouterr().out
        assert "every 30s" in out
        assert "cancelled" in out

    def test_unknown_workflow_is_404_returns_1(self, fake_client, capsys):
        fake_client.install(respond=lambda m, p, j: FakeResponse(404))
        exit_code = stagerunner.main(["recurring", "list", "does_not_exist"])
        assert exit_code == 1
        assert "no workflow" in capsys.readouterr().err


class TestRecurringCancel:
    def test_cancels_and_prints_confirmation(self, fake_client, capsys):
        fake_client.install(respond=lambda m, p, j: FakeResponse(204))
        exit_code = stagerunner.main(["recurring", "cancel", "feed_success", "1"])
        assert exit_code == 0
        assert "cancelled" in capsys.readouterr().out

    def test_unknown_schedule_is_404_returns_1(self, fake_client, capsys):
        fake_client.install(respond=lambda m, p, j: FakeResponse(404, {"detail": "no recurring schedule 999"}))
        exit_code = stagerunner.main(["recurring", "cancel", "feed_success", "999"])
        assert exit_code == 1
        assert "no recurring schedule 999" in capsys.readouterr().err
