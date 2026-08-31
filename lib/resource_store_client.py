"""What a caller needs from the Resource Store, as a Protocol -- so code
that depends on it (e.g. the Scheduler's Runner) can be unit-tested against
an in-memory fake instead of a real HTTP call.

`HttpResourceClient` is the real adapter, talking to resource_store's REST
API over the network. This module lives in lib/, shared by any service that
needs it rather than owned by any one consumer -- add lib/ to sys.path to
use it.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx


class ResourceClient(Protocol):
    def create_resource_if_missing(self, name: str) -> None: ...

    def upload_version(self, name: str, value: Any) -> int:
        """Returns the new version number."""
        ...

    def update_dependencies(self, name: str, version: int, depends_on: list[tuple[str, int]]) -> None: ...

    def promote(self, name: str, version: int) -> None: ...

    def get(self, name: str) -> tuple[int, Any]:
        """Returns (version, value) of the current version."""
        ...


class HttpResourceClient:
    def __init__(self, base_url: str):
        self._http = httpx.Client(base_url=base_url)

    def create_resource_if_missing(self, name: str) -> None:
        response = self._http.post("/resources", json={"name": name})
        if response.status_code not in (201, 409):
            response.raise_for_status()

    def upload_version(self, name: str, value: Any) -> int:
        response = self._http.post(f"/resources/{name}/versions", json={"value": value})
        response.raise_for_status()
        return response.json()["version"]

    def update_dependencies(self, name: str, version: int, depends_on: list[tuple[str, int]]) -> None:
        response = self._http.put(
            f"/resources/{name}/versions/{version}/dependencies",
            json={"depends_on": [list(pair) for pair in depends_on]},
        )
        response.raise_for_status()

    def promote(self, name: str, version: int) -> None:
        response = self._http.post(f"/resources/{name}/promotions", json={"version": version})
        response.raise_for_status()

    def get(self, name: str) -> tuple[int, Any]:
        response = self._http.get(f"/resources/{name}")
        response.raise_for_status()
        body = response.json()
        return body["version"]["version"], body["value"]


class InMemoryResourceClient:
    """Fake for tests: same contract, no network."""

    def __init__(self) -> None:
        self._current: dict[str, tuple[int, Any]] = {}
        self._next_version: dict[str, int] = {}
        self.dependencies_recorded: dict[tuple[str, int], list[tuple[str, int]]] = {}

    def create_resource_if_missing(self, name: str) -> None:
        self._next_version.setdefault(name, 1)

    def upload_version(self, name: str, value: Any) -> int:
        version = self._next_version.get(name, 1)
        self._next_version[name] = version + 1
        self._current[name] = (version, value)
        return version

    def update_dependencies(self, name: str, version: int, depends_on: list[tuple[str, int]]) -> None:
        self.dependencies_recorded[(name, version)] = list(depends_on)

    def promote(self, name: str, version: int) -> None:
        pass  # upload_version already made it current in this fake

    def get(self, name: str) -> tuple[int, Any]:
        return self._current[name]
