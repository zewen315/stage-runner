from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Resource:
    """A registered resource -- the thing that has versions, identified by name."""

    id: int
    name: str
    current_version_id: int | None


@dataclass(frozen=True)
class ResourceVersion:
    """Metadata for one immutable, append-only version of a resource."""

    id: int
    resource_id: int
    version: int
    storage_uri: str
    created_at: str
    is_test: bool


@dataclass(frozen=True)
class ResourceSnapshot:
    """A resource version plus its materialized value (metadata + blob)."""

    version: ResourceVersion
    value: Any
