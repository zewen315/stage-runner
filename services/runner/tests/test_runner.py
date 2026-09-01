import json

import pytest
from resource_store_client import InMemoryResourceClient

from runner import Runner
from stages import StageRegistry


@pytest.fixture
def resources():
    return InMemoryResourceClient()


def test_import_stage_uploads_file_contents(tmp_path, resources):
    input_path = tmp_path / "raw.json"
    input_path.write_text(json.dumps({"n": 1}))

    registry = StageRegistry()
    registry.import_stage("raw", path=str(input_path))

    Runner(resources).run_stage(registry.get("raw"), {}, promote=True)

    assert resources.get("raw") == (1, {"n": 1})


def test_import_path_resolves_relative_to_workflow_dir(tmp_path, resources):
    (tmp_path / "raw.json").write_text(json.dumps({"n": 1}))

    registry = StageRegistry()
    registry.import_stage("raw", path="raw.json")  # relative, not absolute

    Runner(resources, workflow_dir=tmp_path).run_stage(registry.get("raw"), {}, promote=True)

    assert resources.get("raw") == (1, {"n": 1})


def test_stage_fn_receives_dependency_values_and_uploads_return_value(resources):
    resources.upload_version("raw", {"n": 3})
    resources.promote("raw", 1)

    registry = StageRegistry()

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return {"n": raw["n"] * 2}

    output_version = Runner(resources).run_stage(registry.get("doubled"), {}, promote=True)

    assert output_version == 1
    assert resources.get("doubled") == (1, {"n": 6})


def test_stage_records_dependency_versions_used(resources):
    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)

    registry = StageRegistry()

    @registry.stage("plus_one", depends_on=["raw"])
    def plus_one(raw):
        return {"n": raw["n"] + 1}

    Runner(resources).run_stage(registry.get("plus_one"), {}, promote=True)

    assert resources.dependencies_recorded[("plus_one", 1)] == [("raw", 1)]


def test_export_stage_writes_current_value_to_file(tmp_path, resources):
    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)
    output_path = tmp_path / "out.json"

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path=str(output_path))

    output_version = Runner(resources).run_stage(registry.get("publish"), {}, promote=True)

    assert output_version is None
    assert json.loads(output_path.read_text()) == {"n": 1}


def test_export_creates_missing_parent_directories(tmp_path, resources):
    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)
    output_path = tmp_path / "nested" / "dir" / "out.json"

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path=str(output_path))

    Runner(resources).run_stage(registry.get("publish"), {}, promote=True)

    assert output_path.exists()


def test_export_path_resolves_relative_to_output_dir_not_workflow_dir(tmp_path, resources):
    """workflow_dir is checked-in content (read-only in production); export
    paths must never resolve against it, even by accident."""
    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)
    workflow_dir = tmp_path / "workflow"
    output_dir = tmp_path / "output"
    workflow_dir.mkdir()
    output_dir.mkdir()

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path="out.json")

    Runner(resources, workflow_dir=workflow_dir, output_dir=output_dir).run_stage(
        registry.get("publish"), {}, promote=True
    )

    assert (output_dir / "out.json").exists()
    assert not (workflow_dir / "out.json").exists()


def test_output_dir_defaults_to_workflow_dir_when_not_given(tmp_path, resources):
    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path="out.json")

    Runner(resources, workflow_dir=tmp_path).run_stage(registry.get("publish"), {}, promote=True)

    assert (tmp_path / "out.json").exists()


def test_promote_false_uploads_but_does_not_become_current(resources):
    registry = StageRegistry()

    @registry.stage("computed", depends_on=[])
    def computed():
        return {"n": 1}

    version = Runner(resources).run_stage(registry.get("computed"), {}, promote=False)

    assert version == 1
    assert resources.get_version("computed", version) == {"n": 1}
    with pytest.raises(KeyError):
        resources.get("computed")


def test_pinned_input_version_is_used_instead_of_current(resources):
    resources.upload_version("raw", {"n": 1})  # v1, historical
    resources.upload_version("raw", {"n": 99})  # v2
    resources.promote("raw", 2)  # current is v2

    registry = StageRegistry()

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return {"n": raw["n"] * 2}

    Runner(resources).run_stage(registry.get("doubled"), {"raw": 1}, promote=True)

    assert resources.get("doubled") == (1, {"n": 2})  # used pinned v1, not current v2


def test_is_test_flag_threaded_to_upload(resources):
    registry = StageRegistry()

    @registry.stage("computed", depends_on=[])
    def computed():
        return {"n": 1}

    version = Runner(resources).run_stage(registry.get("computed"), {}, promote=False, is_test=True)

    assert resources.is_test_by_version[("computed", version)] is True


def test_stage_execution_goes_through_the_injected_executor(resources):
    """Confirms the seam is real -- run_stage never calls stage_def.fn
    directly, it always goes through whatever StageExecutor was given
    (InProcessStageExecutor by default, which is what every other test
    here implicitly exercises)."""

    class RecordingExecutor:
        def __init__(self):
            self.calls = []

        def run(self, stage_def, inputs, *, workflow_name):
            self.calls.append((stage_def.name, inputs, workflow_name))
            return {"n": 42}

    executor = RecordingExecutor()
    registry = StageRegistry()
    registry.import_stage("raw", path="unused.json")

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        raise AssertionError("should never actually run -- the executor is faked")

    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)

    version = Runner(resources, executor=executor).run_stage(registry.get("doubled"), {}, promote=True)

    assert executor.calls == [("doubled", {"raw": {"n": 1}}, None)]
    assert resources.get("doubled") == (version, {"n": 42})
