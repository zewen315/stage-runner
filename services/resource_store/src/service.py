"""Domain logic for the resource store: upload a version, record what a
version depends on, and promote a version to current -- gated by each
resource's declared contract (see resources/<name>.py at the repo root,
loaded via `validators`). A resource with no declared contract can't be
uploaded to at all; see `ResourceValidatorLoader` in ports.py. There's no
separate "create a resource" step -- a resource's identity comes entirely
from its resources/<name>.py file, the same way a workflow's identity
comes from its workflows/<name>/ directory; the DB only starts tracking a
name once something is actually uploaded to it.
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

    # -- the core operations --------------------------------------------

    def upload_version(self, name: str, value: Any, is_test: bool = False) -> ResourceVersion:
        """Validates against the resource's declared contract, then writes
        the value to blob storage, then records it as a new, immutable
        version. Validation happens before anything is written -- an
        invalid value never becomes a version at all, and no DB row gets
        created for a name that isn't actually declared in code. The blob
        is written before the metadata row so a failure between the two
        steps leaves an orphaned blob (harmless) rather than a metadata row
        pointing at a blob that was never written. Does not promote.
        `is_test` marks a version produced by a standalone/ad-hoc StageRun
        rather than an orchestrated one, so version history can tell real
        pipeline output from manual probes."""
        validate = self._validators.load(name)
        try:
            validate(value)
        except ResourceValidationError:
            raise
        except Exception as exc:
            raise ResourceValidationError(f"{name!r} failed validation: {exc}") from exc

        resource = self._metadata.get_or_create_resource(name)
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
        """Every declared resource (resources/<name>.py), not just ones
        already uploaded to -- a name with no DB row yet just means
        `current_version_id` is None. A handful of names in practice, so a
        get_resource() per name is simpler than a batch-lookup method."""
        return [
            self._metadata.get_resource(name) or Resource(id=None, name=name, current_version_id=None)
            for name in self._validators.list_names()
        ]

    def list_versions(self, name: str) -> list[ResourceVersion]:
        """Unlike `_require_resource`'s other callers, a declared resource
        with no versions yet isn't an error here -- same as
        WorkflowService.list_runs() for a workflow with no runs yet."""
        if name not in self._validators.list_names():
            raise ResourceNotFoundError(f"resource {name!r} has no declared contract")
        resource = self._metadata.get_resource(name)
        return self._metadata.list_versions(resource.id) if resource is not None else []

    # -- internal helpers ----------------------------------------------

    def _require_resource(self, name: str) -> Resource:
        resource = self._metadata.get_resource(name)
        if resource is None:
            if name not in self._validators.list_names():
                raise ResourceNotFoundError(f"resource {name!r} has no declared contract")
            raise ResourceNotFoundError(f"resource {name!r} exists but has no versions yet")
        return resource

    def _require_version(self, resource: Resource, version: int) -> ResourceVersion:
        record = self._metadata.get_version(resource.id, version)
        if record is None:
            raise ResourceNotFoundError(f"no version {version} for resource {resource.name!r}")
        return record
