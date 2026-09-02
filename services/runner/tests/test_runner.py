import pytest
from resource_store_client import InMemoryResourceClient

from runner import Runner
from stages import StageRegistry


@pytest.fixture
def resources():
    return InMemoryResourceClient()


def test_stage_with_no_dependencies_uploads_its_return_value(resources):
    """A workflow root: no dependencies, nothing to resolve -- just runs
    and produces a resource, same as any other stage."""
    registry = StageRegistry()

    @registry.stage("raw", depends_on=[])
    def raw():
        return {"n": 1}

    Runner(resources).run_stage(registry.get("raw"), {}, promote=True)

    assert resources.get("raw") == (1, {"n": 1})


def test_stage_fn_receives_dependency_values_and_uploads_return_value(resources):
    resources.upload_version("raw", {"n": 3})
    resources.promote("raw", 1)

    registry = StageRegistry()

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        return {"n": raw["n"] * 2}

    outcome = Runner(resources).run_stage(registry.get("doubled"), {}, promote=True)

    assert outcome.version == 1
    assert outcome.attempts == 1
    assert outcome.error is None
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


def test_promote_false_uploads_but_does_not_become_current(resources):
    registry = StageRegistry()

    @registry.stage("computed", depends_on=[])
    def computed():
        return {"n": 1}

    outcome = Runner(resources).run_stage(registry.get("computed"), {}, promote=False)

    assert outcome.version == 1
    assert resources.get_version("computed", outcome.version) == {"n": 1}
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

    outcome = Runner(resources).run_stage(registry.get("computed"), {}, promote=False, is_test=True)

    assert resources.is_test_by_version[("computed", outcome.version)] is True


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

    @registry.stage("doubled", depends_on=["raw"])
    def doubled(raw):
        raise AssertionError("should never actually run -- the executor is faked")

    resources.upload_version("raw", {"n": 1})
    resources.promote("raw", 1)

    outcome = Runner(resources, executor=executor).run_stage(registry.get("doubled"), {}, promote=True)

    assert executor.calls == [("doubled", {"raw": {"n": 1}}, None)]
    assert resources.get("doubled") == (outcome.version, {"n": 42})


class TestRetries:
    def test_no_retries_by_default_fails_after_one_attempt(self, resources):
        registry = StageRegistry()
        calls = []

        @registry.stage("flaky", depends_on=[])
        def flaky():
            calls.append(1)
            raise ValueError("boom")

        outcome = Runner(resources).run_stage(registry.get("flaky"), {}, promote=True)

        assert len(calls) == 1
        assert outcome.version is None
        assert outcome.attempts == 1
        assert "boom" in outcome.error

    def test_succeeds_on_a_later_attempt(self, resources):
        registry = StageRegistry()
        calls = []

        @registry.stage("flaky", depends_on=[], retries=2)
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("boom")
            return {"n": 1}

        outcome = Runner(resources).run_stage(registry.get("flaky"), {}, promote=True)

        assert len(calls) == 3
        assert outcome.attempts == 3
        assert outcome.error is None
        assert resources.get("flaky") == (outcome.version, {"n": 1})

    def test_exhausts_retries_and_reports_the_last_error(self, resources):
        registry = StageRegistry()
        calls = []

        @registry.stage("always_fails", depends_on=[], retries=2)
        def always_fails():
            calls.append(1)
            raise ValueError(f"attempt {len(calls)} failed")

        outcome = Runner(resources).run_stage(registry.get("always_fails"), {}, promote=True)

        assert len(calls) == 3  # initial attempt + 2 retries
        assert outcome.version is None
        assert outcome.attempts == 3
        assert "attempt 3 failed" in outcome.error

    def test_each_attempt_re_executes_the_stage_not_just_the_upload(self, resources):
        """Retry re-runs the whole stage function -- not just a re-attempt
        at uploading the same value -- since the point is a fresh call
        might behave differently."""
        registry = StageRegistry()
        calls = []

        @registry.stage("flaky", depends_on=[], retries=1)
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError("boom")
            return {"attempt": len(calls)}

        outcome = Runner(resources).run_stage(registry.get("flaky"), {}, promote=True)

        assert resources.get("flaky") == (outcome.version, {"attempt": 2})
