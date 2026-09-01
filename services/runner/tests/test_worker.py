import json

import pytest
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

    def __call__(self, workflow_name, stage_run_id, action, body):
        self.calls.append((workflow_name, stage_run_id, action, body))


def _message(
    stage_run_id, workflow_name, stage_name, *, input_versions=None, promote=True, workflow_run_id=1
):
    return {
        "stage_run_id": stage_run_id,
        "workflow_run_id": workflow_run_id,
        "workflow_name": workflow_name,
        "stage_name": stage_name,
        "input_versions": input_versions or {},
        "promote": promote,
    }


def test_successful_stage_reports_start_then_complete_with_output_version(tmp_path):
    # Each test uses a distinct workflow name: importlib caches modules by
    # name in sys.modules, so reusing a name across tests (even under
    # different tmp_path roots) would silently return a stale module.
    _write_simple_workflow(tmp_path, name="simple_ok")
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        _message(1, "simple_ok", "raw"),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls == [
        ("simple_ok", 1, "start", {}),
        ("simple_ok", 1, "complete", {"output_version": 1}),
    ]
    assert resources.get("raw") == (1, {"n": 1})


def test_only_the_named_stage_runs_not_the_whole_workflow(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_one_stage")
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        _message(1, "simple_one_stage", "raw"),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    # "doubled" depends on "raw" and was never dispatched -- confirms the
    # worker only executes the one stage named in the message
    with pytest.raises(KeyError):
        resources.get("doubled")


def test_pinned_input_version_is_resolved_instead_of_current(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_pinned")
    resources = InMemoryResourceClient()
    resources.upload_version("raw", {"n": 100})  # v1, never used by this workflow's import stage
    report = RecordingReport()

    process_message(
        _message(1, "simple_pinned", "doubled", input_versions={"raw": 1}),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls[-1] == ("simple_pinned", 1, "complete", {"output_version": 1})
    assert resources.get("doubled") == (1, {"n": 200})


def test_promote_false_does_not_promote(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_no_promote")
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        _message(1, "simple_no_promote", "raw", promote=False),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls[-1][2] == "complete"
    with pytest.raises(KeyError):
        resources.get("raw")
    assert resources.get_version("raw", 1) == {"n": 1}


def test_promote_false_marks_the_version_is_test(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_not_promoted")
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        _message(1, "simple_not_promoted", "raw", promote=False),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert resources.is_test_by_version[("raw", 1)] is True


def test_promote_true_does_not_mark_the_version_is_test(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_promoted")
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        _message(1, "simple_promoted", "raw", promote=True),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert resources.is_test_by_version[("raw", 1)] is False


def test_failing_stage_reports_start_then_fail_with_error(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_boom", boom=True)
    resources = InMemoryResourceClient()
    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)
    report = RecordingReport()

    process_message(
        _message(2, "simple_boom", "doubled"),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls[0] == ("simple_boom", 2, "start", {})
    assert report.calls[1][:3] == ("simple_boom", 2, "fail")
    assert "boom" in report.calls[1][3]["error"]


def test_missing_workflow_reports_fail_without_raising(tmp_path):
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        _message(3, "does_not_exist", "raw"),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls[0] == ("does_not_exist", 3, "start", {})
    assert report.calls[1][2] == "fail"


def test_unknown_stage_name_reports_fail_without_raising(tmp_path):
    _write_simple_workflow(tmp_path, name="simple_unknown_stage")
    resources = InMemoryResourceClient()
    report = RecordingReport()

    process_message(
        _message(4, "simple_unknown_stage", "does_not_exist"),
        workflows_root=tmp_path,
        output_root=tmp_path / "output",
        resources=resources,
        report=report,
    )

    assert report.calls[0] == ("simple_unknown_stage", 4, "start", {})
    assert report.calls[1][2] == "fail"
