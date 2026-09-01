import pytest

from errors import ResourceAlreadyExistsError, ResourceNotFoundError, ResourceValidationError
from memory import InMemoryBlobStore, InMemoryMetadataRepository, InMemoryResourceValidatorLoader
from scenario import Step, run
from service import ResourceStoreService


@pytest.fixture
def validators():
    loader = InMemoryResourceValidatorLoader()
    # permissive by default -- these tests are about metadata/blob/promotion
    # behavior, not validation itself (see TestUploadVersionValidation below)
    loader.register("fetch", lambda value: None)
    loader.register("transform", lambda value: None)
    return loader


@pytest.fixture
def service(validators):
    return ResourceStoreService(InMemoryMetadataRepository(), InMemoryBlobStore(), validators)


class TestCreateResource:
    def test_creates_a_new_resource(self, service):
        run(
            service,
            [
                Step(
                    "create_resource",
                    ["fetch"],
                    expect=lambda r: (r.name, r.current_version_id) == ("fetch", None),
                ),
            ],
        )

    def test_duplicate_name_raises(self, service):
        run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("create_resource", ["fetch"], raises=ResourceAlreadyExistsError),
            ],
        )


class TestUploadVersion:
    def test_first_upload_is_version_one(self, service):
        run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("upload_version", ["fetch", {"n": 1}], expect=lambda v: v.version == 1),
            ],
        )

    def test_uploads_are_sequential(self, service):
        results = run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("upload_version", ["fetch", {"n": 2}], name="v2"),
            ],
        )
        assert (results["v1"].version, results["v2"].version) == (1, 2)

    def test_upload_does_not_promote(self, service):
        run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("upload_version", ["fetch", {"n": 1}]),
                Step("get", ["fetch"], raises=ResourceNotFoundError),
            ],
        )

    def test_upload_to_unknown_resource_raises(self, service):
        run(service, [Step("upload_version", ["fetch", {"n": 1}], raises=ResourceNotFoundError)])


class TestUploadVersionValidation:
    def test_invalid_value_raises_and_nothing_is_persisted(self, service, validators):
        validators.register("fetch", lambda value: (_ for _ in ()).throw(ValueError("bad shape")))
        run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("upload_version", ["fetch", {"n": 1}], raises=ResourceValidationError),
            ],
        )
        # confirms the failed attempt never consumed a version number --
        # nothing was actually persisted, not just "not promoted"
        validators.register("fetch", lambda value: None)
        run(service, [Step("upload_version", ["fetch", {"n": 1}], expect=lambda v: v.version == 1)])

    def test_undeclared_resource_raises(self, service, validators):
        run(
            service,
            [
                Step("create_resource", ["undeclared"]),
                Step("upload_version", ["undeclared", {"n": 1}], raises=ResourceValidationError),
            ],
        )


class TestUpdateDependencies:
    def test_records_direct_dependencies(self, service):
        results = run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("create_resource", ["transform"]),
                Step("upload_version", ["fetch", {"n": 1}], name="upstream"),
                Step("upload_version", ["transform", {"n": 2}], name="downstream"),
                Step(
                    "update_dependencies",
                    [
                        "transform",
                        lambda r: r["downstream"].version,
                        lambda r: [("fetch", r["upstream"].version)],
                    ],
                ),
                Step("dependencies", ["transform", lambda r: r["downstream"].version], name="deps"),
            ],
        )
        assert [d.id for d in results["deps"]] == [results["upstream"].id]

    def test_update_replaces_the_previous_set(self, service):
        results = run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("create_resource", ["transform"]),
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("upload_version", ["fetch", {"n": 2}], name="v2"),
                Step("upload_version", ["transform", {"n": 3}], name="downstream"),
                Step(
                    "update_dependencies",
                    ["transform", lambda r: r["downstream"].version, lambda r: [("fetch", r["v1"].version)]],
                ),
                Step(
                    "update_dependencies",
                    ["transform", lambda r: r["downstream"].version, lambda r: [("fetch", r["v2"].version)]],
                ),
                Step("dependencies", ["transform", lambda r: r["downstream"].version], name="deps"),
            ],
        )
        assert [d.id for d in results["deps"]] == [results["v2"].id]

    def test_unknown_upstream_resource_raises(self, service):
        run(
            service,
            [
                Step("create_resource", ["transform"]),
                Step("upload_version", ["transform", {"n": 1}], name="downstream"),
                Step(
                    "update_dependencies",
                    ["transform", lambda r: r["downstream"].version, [("fetch", 1)]],
                    raises=ResourceNotFoundError,
                ),
            ],
        )

    def test_unknown_upstream_version_raises(self, service):
        run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("create_resource", ["transform"]),
                Step("upload_version", ["transform", {"n": 1}], name="downstream"),
                Step(
                    "update_dependencies",
                    ["transform", lambda r: r["downstream"].version, [("fetch", 99)]],
                    raises=ResourceNotFoundError,
                ),
            ],
        )


class TestPromote:
    def test_promote_makes_a_version_current(self, service):
        results = run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("promote", ["fetch", lambda r: r["v1"].version]),
                Step("get", ["fetch"], name="current", expect=lambda snap: snap.value == {"n": 1}),
            ],
        )
        assert results["current"].version.version == results["v1"].version

    def test_promote_unknown_version_raises(self, service):
        run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("promote", ["fetch", 99], raises=ResourceNotFoundError),
            ],
        )

    def test_promoting_a_later_version_replaces_current(self, service):
        results = run(
            service,
            [
                Step("create_resource", ["fetch"]),
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("upload_version", ["fetch", {"n": 2}], name="v2"),
                Step("promote", ["fetch", lambda r: r["v1"].version]),
                Step("promote", ["fetch", lambda r: r["v2"].version]),
                Step("get", ["fetch"], name="current"),
            ],
        )
        assert results["current"].value == {"n": 2}
