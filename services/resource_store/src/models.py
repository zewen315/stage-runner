from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Resource:
    """A resource, identified by name -- its identity comes from code
    (resources/<name>.py), not this row. `id` is None when the name is
    declared but has never been uploaded to yet, so no DB row exists."""

    id: int | None
    name: str
    current_version_id: int | None


@dataclass(frozen=True)
class ResourceVersion:
    """Metadata for one immutable, append-only version of a resource.
    `validation_error` is None if the value passed its resource's declared
    contract at upload time, otherwise the reason it didn't -- recorded,
    not rejected: the version is persisted either way (see
    ResourceStoreService.upload_version), so a bad value stays inspectable
    instead of just an error message nobody kept."""

    id: int
    resource_id: int
    name: str
    version: int
    storage_uri: str
    created_at: str
    is_test: bool
    validation_error: str | None


@dataclass(frozen=True)
class ResourceSnapshot:
    """A resource version plus its materialized value (metadata + blob)."""

    version: ResourceVersion
    value: Any
