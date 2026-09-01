import json

from resource_store_client import InMemoryResourceClient

from worker import process_message


def _write_simple_workflow(workflows_root, name="simple", *, boom=False):
    """A minimal one-stage workflow package: import -> stage."""
    workflow_dir = workflows_root / name
    workflow_dir.mkdir()
    (workflow_dir / "data").mkdir()
    (workflow_dir / "data" / "raw.json").write_text(json.dumps({"n": 1}))

    body = 'raise ValueError("boom")' if boom else "return {'n': raw['n'] * 2}"
    (workflow_dir / "__init__.py").write_text(
        f"""
from stages import StageRegistry

registry = StageRegistry()
registry.import_stage("raw", path="data/raw.json")


@registry.stage("doubled", depends_on=["raw"])
def doubled(raw):
    {body}
"""
    )
    return workflow_dir


class RecordingReport:
    def __init__(self):
        self.calls: list[tuple[str, int, str, dict]] = []

    def __call__(self, workflow_name, run_id, action, body):
        self.calls.append((workflow_name, run_id, action, body))


def test_successful_run_reports_start_then_complete(tmp_path):
    # Each test uses a distinct workflow name: importlib caches modules by
    # name in sys.modules, so reusing a name across tests (even under
    # different tmp_path roots) would silently return a stale module.
    _write_simple_workflow(tmp_path, name="simple_ok")
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        {"run_id": 1, "workflow_name": "simple_ok"},
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls == [
        ("simple_ok", 1, "start", {}),
        ("simple_ok", 1, "complete", {}),
    ]
    assert resources.get("doubled") == (1, {"n": 2})


def test_failing_stage_reports_start_then_fail_with_error(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_boom", boom=True)
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        {"run_id": 2, "workflow_name": "simple_boom"},
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls[0] == ("simple_boom", 2, "start", {})
    assert report.calls[1][:3] == ("simple_boom", 2, "fail")
    assert "doubled" in report.calls[1][3]["error"]
    assert "boom" in report.calls[1][3]["error"]


def test_missing_workflow_reports_fail_without_raising(tmp_path):
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        {"run_id": 3, "workflow_name": "does_not_exist"},
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls[0] == ("does_not_exist", 3, "start", {})
    assert report.calls[1][2] == "fail"
