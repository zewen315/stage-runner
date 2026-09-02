import pytest

from errors import ResourceNotFoundError, ResourceValidationError
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


class TestUploadVersion:
    def test_first_upload_is_version_one(self, service):
        run(service, [Step("upload_version", ["fetch", {"n": 1}], expect=lambda v: v.version == 1)])

    def test_uploads_are_sequential(self, service):
        results = run(
            service,
            [
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("upload_version", ["fetch", {"n": 2}], name="v2"),
            ],
        )
        assert (results["v1"].version, results["v2"].version) == (1, 2)

    def test_upload_does_not_promote(self, service):
        run(
            service,
            [
                Step("upload_version", ["fetch", {"n": 1}]),
                Step("get", ["fetch"], raises=ResourceNotFoundError),
            ],
        )

    def test_first_upload_auto_creates_the_resource(self, service):
        """No separate "create" step -- resource identity comes from
        code (the `validators` fixture declares "fetch"); the first
        upload is what makes it start appearing with real DB state."""
        run(service, [Step("upload_version", ["fetch", {"n": 1}])])

        resource = next(r for r in service.list_resources() if r.name == "fetch")
        assert resource.id is not None


class TestUploadVersionValidation:
    def test_invalid_value_still_persists_with_the_error_recorded(self, service, validators):
        validators.register("fetch", lambda value: (_ for _ in ()).throw(ValueError("bad shape")))
        run(service, [Step("upload_version", ["fetch", {"n": 1}], raises=ResourceValidationError)])

        versions = service.list_versions("fetch")
        assert len(versions) == 1
        assert versions[0].version == 1
        assert "bad shape" in versions[0].validation_error

        # confirms the failed attempt still consumed version 1 -- the next
        # (now valid) upload is version 2, not a reused 1
        validators.register("fetch", lambda value: None)
        run(service, [Step("upload_version", ["fetch", {"n": 1}], expect=lambda v: v.version == 2)])

    def test_valid_value_records_no_validation_error(self, service):
        run(
            service,
            [
                Step(
                    "upload_version",
                    ["fetch", {"n": 1}],
                    expect=lambda v: v.validation_error is None,
                )
            ],
        )

    def test_undeclared_resource_raises(self, service):
        """Unlike a declared-but-failing value, there's no contract to
        record a result against at all -- this is the one case that still
        can't persist anything."""
        run(service, [Step("upload_version", ["undeclared", {"n": 1}], raises=ResourceValidationError)])


class TestUpdateDependencies:
    def test_records_direct_dependencies(self, service):
        results = run(
            service,
            [
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
        """"fetch" is declared (see the `validators` fixture) but never
        uploaded to -- update_dependencies still can't point at it."""
        run(
            service,
            [
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
                Step("upload_version", ["fetch", {"n": 1}]),
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
                Step("upload_version", ["fetch", {"n": 1}]),
                Step("promote", ["fetch", 99], raises=ResourceNotFoundError),
            ],
        )

    def test_promoting_a_later_version_replaces_current(self, service):
        results = run(
            service,
            [
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("upload_version", ["fetch", {"n": 2}], name="v2"),
                Step("promote", ["fetch", lambda r: r["v1"].version]),
                Step("promote", ["fetch", lambda r: r["v2"].version]),
                Step("get", ["fetch"], name="current"),
            ],
        )
        assert results["current"].value == {"n": 2}


class TestListResources:
    def test_lists_every_declared_resource_even_with_no_versions_uploaded(self, service):
        """The `validators` fixture declares "fetch" and "transform" --
        both should show up, since resource identity now comes from code,
        not from anything ever being uploaded."""
        assert [(r.name, r.current_version_id) for r in service.list_resources()] == [
            ("fetch", None),
            ("transform", None),
        ]

    def test_reflects_current_version_once_uploaded_and_promoted(self, service):
        results = run(
            service,
            [
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("promote", ["fetch", lambda r: r["v1"].version]),
            ],
        )

        by_name = {r.name: r.current_version_id for r in service.list_resources()}
        assert by_name["fetch"] == results["v1"].id
        assert by_name["transform"] is None


class TestListVersions:
    def test_empty_when_no_versions_uploaded(self, service):
        assert service.list_versions("fetch") == []

    def test_lists_versions_oldest_to_newest(self, service):
        results = run(
            service,
            [
                Step("upload_version", ["fetch", {"n": 1}], name="v1"),
                Step("upload_version", ["fetch", {"n": 2}], name="v2"),
            ],
        )

        versions = service.list_versions("fetch")
        assert [v.id for v in versions] == [results["v1"].id, results["v2"].id]

    def test_undeclared_resource_raises(self, service):
        with pytest.raises(ResourceNotFoundError):
            service.list_versions("does_not_exist")
