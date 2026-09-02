"""In-memory adapters for MetadataRepository, BlobStore, and
ResourceValidatorLoader.

Used by unit tests (and available for local scripting) so the domain logic
in ResourceStoreService can be exercised without Postgres, MinIO, or a real
resources/ directory on disk.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import replace
from typing import Any, Callable

from errors import ResourceValidationError
from models import Resource, ResourceVersion


class InMemoryMetadataRepository:
    def __init__(self) -> None:
        self._resources: dict[int, Resource] = {}
        self._resource_ids_by_name: dict[str, int] = {}
        self._next_resource_id = 1

        self._versions: dict[int, ResourceVersion] = {}
        self._version_ids_by_resource: dict[int, dict[int, int]] = defaultdict(dict)
        self._next_version_id = 1

        self._dependencies: dict[int, list[int]] = {}

    def get_or_create_resource(self, name: str) -> Resource:
        resource_id = self._resource_ids_by_name.get(name)
        if resource_id is not None:
            return self._resources[resource_id]

        resource_id = self._next_resource_id
        self._next_resource_id += 1
        resource = Resource(id=resource_id, name=name, current_version_id=None)
        self._resources[resource_id] = resource
        self._resource_ids_by_name[name] = resource_id
        return resource

    def get_resource(self, name: str) -> Resource | None:
        resource_id = self._resource_ids_by_name.get(name)
        return self._resources.get(resource_id) if resource_id is not None else None

    def next_version(self, resource_id: int) -> int:
        existing = self._version_ids_by_resource[resource_id]
        return (max(existing) if existing else 0) + 1

    def record_version(
        self,
        resource_id: int,
        version: int,
        storage_uri: str,
        created_at: str,
        is_test: bool = False,
        validation_error: str | None = None,
    ) -> ResourceVersion:
        version_id = self._next_version_id
        self._next_version_id += 1
        record = ResourceVersion(
            id=version_id,
            resource_id=resource_id,
            name=self._resources[resource_id].name,
            version=version,
            storage_uri=storage_uri,
            created_at=created_at,
            is_test=is_test,
            validation_error=validation_error,
        )
        self._versions[version_id] = record
        self._version_ids_by_resource[resource_id][version] = version_id
        return record

    def get_version(self, resource_id: int, version: int) -> ResourceVersion | None:
        version_id = self._version_ids_by_resource[resource_id].get(version)
        return self._versions.get(version_id) if version_id is not None else None

    def get_version_by_id(self, version_id: int) -> ResourceVersion | None:
        return self._versions.get(version_id)

    def list_versions(self, resource_id: int) -> list[ResourceVersion]:
        version_ids = self._version_ids_by_resource[resource_id]
        return [self._versions[version_ids[v]] for v in sorted(version_ids)]

    def set_dependencies(self, version_id: int, depends_on_ids: list[int]) -> None:
        self._dependencies[version_id] = list(depends_on_ids)

    def get_dependencies(self, version_id: int) -> list[int]:
        return list(self._dependencies.get(version_id, []))

    def promote(self, resource_id: int, version_id: int) -> None:
        self._resources[resource_id] = replace(
            self._resources[resource_id], current_version_id=version_id
        )


class InMemoryBlobStore:
    def __init__(self) -> None:
        self._blobs: dict[str, Any] = {}

    def put(self, storage_uri: str, value: Any) -> None:
        self._blobs[storage_uri] = copy.deepcopy(value)

    def get(self, storage_uri: str) -> Any:
        return copy.deepcopy(self._blobs[storage_uri])


class InMemoryResourceValidatorLoader:
    def __init__(self) -> None:
        self._validators: dict[str, Callable[[Any], None]] = {}

    def register(self, name: str, validate: Callable[[Any], None]) -> None:
        """Test-seeding helper -- the real loader reads resources/<name>.py
        from disk; tests register a validator directly instead."""
        self._validators[name] = validate

    def load(self, name: str) -> Callable[[Any], None]:
        validate = self._validators.get(name)
        if validate is None:
            raise ResourceValidationError(f"resource {name!r} has no declared contract")
        return validate

    def list_names(self) -> list[str]:
        return sorted(self._validators)
