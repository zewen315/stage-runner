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

    Runner(resources).run(registry.get("raw"))

    assert resources.get("raw") == (1, {"n": 1})


def test_import_path_resolves_relative_to_workflow_dir(tmp_path, resources):
    (tmp_path / "raw.json").write_text(json.dumps({"n": 1}))

    registry = StageRegistry()
    registry.import_stage("raw", path="raw.json")  # relative, not absolute

    Runner(resources, workflow_dir=tmp_path).run(registry.get("raw"))

    assert resources.get("raw") == (1, {"n": 1})


def test_stage_fn_receives_dependency_values_and_uploads_return_value(resources):
    resources.upload_version("raw", {"n": 3})

    registry = StageRegistry()

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return {"n": raw["n"] * 2}

    Runner(resources).run(registry.get("doubled"))

    assert resources.get("doubled") == (1, {"n": 6})


def test_stage_records_dependency_versions_used(resources):
    resources.upload_version("raw", {"n": 1})

    registry = StageRegistry()

    @registry.stage("plus_one", depends_on=["raw"])
    def plus_one(raw):
        return {"n": raw["n"] + 1}

    Runner(resources).run(registry.get("plus_one"))

    assert resources.dependencies_recorded[("plus_one", 1)] == [("raw", 1)]


def test_export_stage_writes_current_value_to_file(tmp_path, resources):
    resources.upload_version("raw", {"n": 1})
    output_path = tmp_path / "out.json"

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path=str(output_path))

    Runner(resources).run(registry.get("publish"))

    assert json.loads(output_path.read_text()) == {"n": 1}


def test_export_creates_missing_parent_directories(tmp_path, resources):
    resources.upload_version("raw", {"n": 1})
    output_path = tmp_path / "nested" / "dir" / "out.json"

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path=str(output_path))

    Runner(resources).run(registry.get("publish"))

    assert output_path.exists()


def test_export_path_resolves_relative_to_output_dir_not_workflow_dir(tmp_path, resources):
    """workflow_dir is checked-in content (read-only in production); export
    paths must never resolve against it, even by accident."""
    resources.upload_version("raw", {"n": 1})
    workflow_dir = tmp_path / "workflow"
    output_dir = tmp_path / "output"
    workflow_dir.mkdir()
    output_dir.mkdir()

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path="out.json")

    Runner(resources, workflow_dir=workflow_dir, output_dir=output_dir).run(registry.get("publish"))

    assert (output_dir / "out.json").exists()
    assert not (workflow_dir / "out.json").exists()


def test_output_dir_defaults_to_workflow_dir_when_not_given(tmp_path, resources):
    resources.upload_version("raw", {"n": 1})

    registry = StageRegistry()
    registry.export_stage("publish", depends_on="raw", path="out.json")

    Runner(resources, workflow_dir=tmp_path).run(registry.get("publish"))

    assert (tmp_path / "out.json").exists()
