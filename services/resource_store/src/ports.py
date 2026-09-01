"""Storage interfaces the service depends on.

Splitting metadata (resources, versions, dependencies) from blob storage
(the actual resource value) mirrors the production split: Postgres for
metadata, S3/MinIO for blobs. Depending on these Protocols instead of
concrete clients keeps ResourceStoreService testable with fast in-memory
fakes, with the real adapters swapped in only when actually running the
service.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from models import Resource, ResourceVersion


class MetadataRepository(Protocol):
    def create_resource(self, name: str) -> Resource:
        """Raises ResourceAlreadyExistsError if `name` is already taken."""
        ...

    def get_resource(self, name: str) -> Resource | None: ...

    def list_resources(self) -> list[Resource]: ...

    def next_version(self, resource_id: int) -> int: ...

    def record_version(
        self, resource_id: int, version: int, storage_uri: str, created_at: str, is_test: bool = False
    ) -> ResourceVersion: ...

    def get_version(self, resource_id: int, version: int) -> ResourceVersion | None: ...

    def get_version_by_id(self, version_id: int) -> ResourceVersion | None: ...

    def list_versions(self, resource_id: int) -> list[ResourceVersion]:
        """All versions of a resource, ordered oldest to newest."""
        ...

    def set_dependencies(self, version_id: int, depends_on_ids: list[int]) -> None:
        """Replace the full set of direct dependencies for `version_id`."""
        ...

    def get_dependencies(self, version_id: int) -> list[int]:
        """Direct dependencies only -- not the transitive chain."""
        ...

    def promote(self, resource_id: int, version_id: int) -> None:
        """Mark `version_id` as the resource's current version."""
        ...


class BlobStore(Protocol):
    def put(self, storage_uri: str, value: Any) -> None: ...

    def get(self, storage_uri: str) -> Any: ...


class ResourceValidatorLoader(Protocol):
    def load(self, name: str) -> Callable[[Any], None]:
        """Raises ResourceValidationError if `name` has no declared
        contract."""
        ...
