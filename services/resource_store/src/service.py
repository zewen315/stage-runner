"""Domain logic for the resource store: create a resource, upload a
version, record what a version depends on, and promote a version to
current -- gated by each resource's declared contract (see
resources/<name>.py at the repo root, loaded via `validators`). A resource
with no declared contract can't be uploaded to at all; see
`ResourceValidatorLoader` in ports.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from errors import ResourceNotFoundError, ResourceValidationError
from models import Resource, ResourceSnapshot, ResourceVersion
from ports import BlobStore, MetadataRepository, ResourceValidatorLoader


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _storage_uri(name: str, version: int) -> str:
    return f"{name}/v{version}.json"


class ResourceStoreService:
    def __init__(self, metadata: MetadataRepository, blobs: BlobStore, validators: ResourceValidatorLoader):
        self._metadata = metadata
        self._blobs = blobs
        self._validators = validators

    # -- the four core operations ------------------------------------

    def create_resource(self, name: str) -> Resource:
        return self._metadata.create_resource(name)

    def upload_version(self, name: str, value: Any, is_test: bool = False) -> ResourceVersion:
        """Validates against the resource's declared contract, then writes
        the value to blob storage, then records it as a new, immutable
        version. Validation happens before anything is written -- an
        invalid value never becomes a version at all. The blob is written
        before the metadata row so a failure between the two steps leaves
        an orphaned blob (harmless) rather than a metadata row pointing at
        a blob that was never written. Does not promote. `is_test` marks a
        version produced by a standalone/ad-hoc StageRun rather than an
        orchestrated one, so version history can tell real pipeline output
        from manual probes."""
        resource = self._require_resource(name)
        validate = self._validators.load(name)
        try:
            validate(value)
        except ResourceValidationError:
            raise
        except Exception as exc:
            raise ResourceValidationError(f"{name!r} failed validation: {exc}") from exc

        version_number = self._metadata.next_version(resource.id)
        storage_uri = _storage_uri(name, version_number)
        self._blobs.put(storage_uri, value)
        return self._metadata.record_version(
            resource_id=resource.id,
            version=version_number,
            storage_uri=storage_uri,
            created_at=_utcnow(),
            is_test=is_test,
        )

    def update_dependencies(self, name: str, version: int, depends_on: list[tuple[str, int]]) -> None:
        """Replace the full set of direct dependencies for (name, version)
        with the given (upstream_name, upstream_version) pairs.

        This records direct edges only, not the transitive chain -- finding
        everything a version ultimately depends on means walking this table,
        which isn't implemented yet (deferred until something needs it)."""
        resource = self._require_resource(name)
        record = self._require_version(resource, version)

        depends_on_ids = [
            self._require_version(self._require_resource(upstream_name), upstream_version).id
            for upstream_name, upstream_version in depends_on
        ]
        self._metadata.set_dependencies(record.id, depends_on_ids)

    def promote(self, name: str, version: int) -> None:
        resource = self._require_resource(name)
        record = self._require_version(resource, version)
        self._metadata.promote(resource.id, record.id)

    # -- minimal read access, needed to exercise the above ------------

    def get(self, name: str, version: int | None = None) -> ResourceSnapshot:
        resource = self._require_resource(name)

        if version is None:
            if resource.current_version_id is None:
                raise ResourceNotFoundError(f"no current version for resource {name!r}")
            record = self._metadata.get_version_by_id(resource.current_version_id)
        else:
            record = self._require_version(resource, version)

        return ResourceSnapshot(version=record, value=self._blobs.get(record.storage_uri))

    def dependencies(self, name: str, version: int) -> list[ResourceVersion]:
        resource = self._require_resource(name)
        record = self._require_version(resource, version)
        return [self._metadata.get_version_by_id(vid) for vid in self._metadata.get_dependencies(record.id)]

    def list_resources(self) -> list[Resource]:
        return self._metadata.list_resources()

    def list_versions(self, name: str) -> list[ResourceVersion]:
        resource = self._require_resource(name)
        return self._metadata.list_versions(resource.id)

    # -- internal helpers ----------------------------------------------

    def _require_resource(self, name: str) -> Resource:
        resource = self._metadata.get_resource(name)
        if resource is None:
            raise ResourceNotFoundError(f"resource {name!r} does not exist")
        return resource

    def _require_version(self, resource: Resource, version: int) -> ResourceVersion:
        record = self._metadata.get_version(resource.id, version)
        if record is None:
            raise ResourceNotFoundError(f"no version {version} for resource {resource.name!r}")
        return record
