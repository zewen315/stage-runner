"""In-memory adapters for MetadataRepository and BlobStore.

Used by unit tests (and available for local scripting) so the domain logic
in ResourceStoreService can be exercised without Postgres or MinIO running.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import replace
from typing import Any

from errors import ResourceAlreadyExistsError
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

    def create_resource(self, name: str) -> Resource:
        if name in self._resource_ids_by_name:
            raise ResourceAlreadyExistsError(f"resource {name!r} already exists")

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
        self, resource_id: int, version: int, storage_uri: str, created_at: str
    ) -> ResourceVersion:
        version_id = self._next_version_id
        self._next_version_id += 1
        record = ResourceVersion(
            id=version_id,
            resource_id=resource_id,
            version=version,
            storage_uri=storage_uri,
            created_at=created_at,
        )
        self._versions[version_id] = record
        self._version_ids_by_resource[resource_id][version] = version_id
        return record

    def get_version(self, resource_id: int, version: int) -> ResourceVersion | None:
        version_id = self._version_ids_by_resource[resource_id].get(version)
        return self._versions.get(version_id) if version_id is not None else None

    def get_version_by_id(self, version_id: int) -> ResourceVersion | None:
        return self._versions.get(version_id)

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
