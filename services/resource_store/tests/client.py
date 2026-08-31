"""Thin HTTP client mirroring ResourceStoreService's method names, so the
same Step/run scenario DSL used for the service-level tests can also drive
the real HTTP API. Unlike the service, each method returns the raw
httpx.Response -- integration tests care about status codes, which the
service layer has no concept of.
"""

from __future__ import annotations

from typing import Any

import httpx


class ResourceStoreClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def create_resource(self, name: str) -> httpx.Response:
        return self._http.post("/resources", json={"name": name})

    def upload_version(self, name: str, value: Any) -> httpx.Response:
        return self._http.post(f"/resources/{name}/versions", json={"value": value})

    def update_dependencies(
        self, name: str, version: int, depends_on: list[tuple[str, int]]
    ) -> httpx.Response:
        return self._http.put(
            f"/resources/{name}/versions/{version}/dependencies",
            json={"depends_on": depends_on},
        )

    def promote(self, name: str, version: int) -> httpx.Response:
        return self._http.post(f"/resources/{name}/promotions", json={"version": version})

    def get(self, name: str, version: int | None = None) -> httpx.Response:
        path = f"/resources/{name}" if version is None else f"/resources/{name}/versions/{version}"
        return self._http.get(path)

    def dependencies(self, name: str, version: int) -> httpx.Response:
        return self._http.get(f"/resources/{name}/versions/{version}/dependencies")
