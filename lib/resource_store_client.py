"""What a caller needs from the Resource Store, as a Protocol -- so code
that depends on it (e.g. the Runner) can be unit-tested against an
in-memory fake instead of a real HTTP call.

`HttpResourceClient` is the real adapter, talking to resource_store's REST
API over the network. This module lives in lib/, shared by any service that
needs it rather than owned by any one consumer -- add lib/ to sys.path to
use it.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx


class ResourceClient(Protocol):
    def upload_version(self, name: str, value: Any, is_test: bool = False) -> int:
        """Returns the new version number. Doesn't make it current -- call
        `promote` separately for that."""
        ...

    def update_dependencies(self, name: str, version: int, depends_on: list[tuple[str, int]]) -> None: ...

    def promote(self, name: str, version: int) -> None: ...

    def get(self, name: str) -> tuple[int, Any]:
        """Returns (version, value) of the current version."""
        ...

    def get_version(self, name: str, version: int) -> Any:
        """Returns the value of a specific, possibly non-current, version."""
        ...


class HttpResourceClient:
    def __init__(self, base_url: str):
        self._http = httpx.Client(base_url=base_url)

    def upload_version(self, name: str, value: Any, is_test: bool = False) -> int:
        response = self._http.post(
            f"/resources/{name}/versions", json={"value": value, "is_test": is_test}
        )
        if response.status_code == 400:
            # resource_store rejected this as a validation failure (no
            # declared contract, or the value failed it) -- surface the
            # actual reason, not just a generic HTTPStatusError, so it
            # makes it all the way to the run's recorded error.
            raise ValueError(response.json().get("detail", response.text))
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

    def get_version(self, name: str, version: int) -> Any:
        response = self._http.get(f"/resources/{name}/versions/{version}")
        response.raise_for_status()
        return response.json()["value"]


class InMemoryResourceClient:
    """Fake for tests: same contract, no network. Retains every uploaded
    version (not just current) so `get_version` can look up history, and
    keeps "current" as an explicit, separate pointer only `promote` moves --
    `upload_version` alone does not make a version current, matching the
    real service."""

    def __init__(self) -> None:
        self._versions: dict[tuple[str, int], Any] = {}
        self._current_version: dict[str, int] = {}
        self._next_version: dict[str, int] = {}
        self.dependencies_recorded: dict[tuple[str, int], list[tuple[str, int]]] = {}
        self.is_test_by_version: dict[tuple[str, int], bool] = {}

    def upload_version(self, name: str, value: Any, is_test: bool = False) -> int:
        version = self._next_version.get(name, 1)
        self._next_version[name] = version + 1
        self._versions[(name, version)] = value
        self.is_test_by_version[(name, version)] = is_test
        return version

    def update_dependencies(self, name: str, version: int, depends_on: list[tuple[str, int]]) -> None:
        self.dependencies_recorded[(name, version)] = list(depends_on)

    def promote(self, name: str, version: int) -> None:
        self._current_version[name] = version

    def get(self, name: str) -> tuple[int, Any]:
        version = self._current_version[name]
        return version, self._versions[(name, version)]

    def get_version(self, name: str, version: int) -> Any:
        return self._versions[(name, version)]
