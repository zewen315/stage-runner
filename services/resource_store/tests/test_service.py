import pytest

from errors import ResourceAlreadyExistsError, ResourceNotFoundError
from memory import InMemoryBlobStore, InMemoryMetadataRepository
from service import ResourceStoreService


@pytest.fixture
def service():
    return ResourceStoreService(InMemoryMetadataRepository(), InMemoryBlobStore())


class TestCreateResource:
    def test_creates_a_new_resource(self, service):
        resource = service.create_resource("fetch")

        assert resource.name == "fetch"
        assert resource.current_version_id is None

    def test_duplicate_name_raises(self, service):
        service.create_resource("fetch")

        with pytest.raises(ResourceAlreadyExistsError):
            service.create_resource("fetch")


class TestUploadVersion:
    def test_first_upload_is_version_one(self, service):
        service.create_resource("fetch")

        version = service.upload_version("fetch", {"n": 1})

        assert version.version == 1

    def test_uploads_are_sequential(self, service):
        service.create_resource("fetch")

        v1 = service.upload_version("fetch", {"n": 1})
        v2 = service.upload_version("fetch", {"n": 2})

        assert (v1.version, v2.version) == (1, 2)

    def test_upload_does_not_promote(self, service):
        service.create_resource("fetch")

        service.upload_version("fetch", {"n": 1})

        with pytest.raises(ResourceNotFoundError):
            service.get("fetch")

    def test_upload_to_unknown_resource_raises(self, service):
        with pytest.raises(ResourceNotFoundError):
            service.upload_version("fetch", {"n": 1})


class TestUpdateDependencies:
    def test_records_direct_dependencies(self, service):
        service.create_resource("fetch")
        service.create_resource("transform")
        upstream = service.upload_version("fetch", {"n": 1})
        downstream = service.upload_version("transform", {"n": 2})

        service.update_dependencies(
            "transform", downstream.version, depends_on=[("fetch", upstream.version)]
        )

        deps = service.dependencies("transform", downstream.version)
        assert [d.id for d in deps] == [upstream.id]

    def test_update_replaces_the_previous_set(self, service):
        service.create_resource("fetch")
        service.create_resource("transform")
        v1 = service.upload_version("fetch", {"n": 1})
        v2 = service.upload_version("fetch", {"n": 2})
        downstream = service.upload_version("transform", {"n": 3})

        service.update_dependencies("transform", downstream.version, depends_on=[("fetch", v1.version)])
        service.update_dependencies("transform", downstream.version, depends_on=[("fetch", v2.version)])

        deps = service.dependencies("transform", downstream.version)
        assert [d.id for d in deps] == [v2.id]

    def test_unknown_upstream_resource_raises(self, service):
        service.create_resource("transform")
        downstream = service.upload_version("transform", {"n": 1})

        with pytest.raises(ResourceNotFoundError):
            service.update_dependencies("transform", downstream.version, depends_on=[("fetch", 1)])

    def test_unknown_upstream_version_raises(self, service):
        service.create_resource("fetch")
        service.create_resource("transform")
        downstream = service.upload_version("transform", {"n": 1})

        with pytest.raises(ResourceNotFoundError):
            service.update_dependencies("transform", downstream.version, depends_on=[("fetch", 99)])


class TestPromote:
    def test_promote_makes_a_version_current(self, service):
        service.create_resource("fetch")
        version = service.upload_version("fetch", {"n": 1})

        service.promote("fetch", version.version)

        current = service.get("fetch")
        assert current.version.version == version.version
        assert current.value == {"n": 1}

    def test_promote_unknown_version_raises(self, service):
        service.create_resource("fetch")

        with pytest.raises(ResourceNotFoundError):
            service.promote("fetch", 99)

    def test_promoting_a_later_version_replaces_current(self, service):
        service.create_resource("fetch")
        v1 = service.upload_version("fetch", {"n": 1})
        v2 = service.upload_version("fetch", {"n": 2})

        service.promote("fetch", v1.version)
        service.promote("fetch", v2.version)

        assert service.get("fetch").value == {"n": 2}
