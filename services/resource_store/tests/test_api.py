"""Integration tests for the HTTP layer. Deliberately narrow: the full
business-logic edge case matrix already lives in test_service.py and
exercising it again here would just be duplicate coverage. What's unique to
this layer -- status code mapping, request/response shape, and that the
routes are wired to the right service methods -- is what's tested here.
"""

import pytest
from fastapi.testclient import TestClient

from api import app, get_service
from client import ResourceStoreClient
from memory import InMemoryBlobStore, InMemoryMetadataRepository, InMemoryResourceValidatorLoader
from scenario import Step, run
from service import ResourceStoreService


@pytest.fixture
def client():
    """A fresh service per test, injected via FastAPI's dependency override
    -- otherwise every test would share the app's module-level singleton
    and pollute each other's resource names."""
    validators = InMemoryResourceValidatorLoader()
    for name in ("widget", "fetch", "transform", "dup"):
        validators.register(name, lambda value: None)
    service = ResourceStoreService(InMemoryMetadataRepository(), InMemoryBlobStore(), validators)
    app.dependency_overrides[get_service] = lambda: service
    yield ResourceStoreClient(TestClient(app))
    app.dependency_overrides.clear()


class TestHappyPath:
    def test_create_upload_promote_and_read(self, client):
        results = run(
            client,
            [
                Step("create_resource", ["widget"], expect=lambda r: r.status_code == 201),
                Step(
                    "upload_version",
                    ["widget", {"n": 1}],
                    name="v1",
                    expect=lambda r: r.status_code == 201,
                ),
                Step(
                    "promote",
                    ["widget", lambda r: r["v1"].json()["version"]],
                    expect=lambda r: r.status_code == 204,
                ),
                Step("get", ["widget"], name="current", expect=lambda r: r.status_code == 200),
            ],
        )
        assert results["current"].json()["value"] == {"n": 1}

    def test_dependencies_round_trip(self, client):
        results = run(
            client,
            [
                Step("create_resource", ["fetch"]),
                Step("create_resource", ["transform"]),
                Step("upload_version", ["fetch", {"n": 1}], name="upstream"),
                Step("upload_version", ["transform", {"n": 2}], name="downstream"),
                Step(
                    "update_dependencies",
                    [
                        "transform",
                        lambda r: r["downstream"].json()["version"],
                        lambda r: [["fetch", r["upstream"].json()["version"]]],
                    ],
                    expect=lambda r: r.status_code == 204,
                ),
                Step(
                    "dependencies",
                    ["transform", lambda r: r["downstream"].json()["version"]],
                    name="deps",
                    expect=lambda r: r.status_code == 200,
                ),
            ],
        )
        assert [d["id"] for d in results["deps"].json()] == [results["upstream"].json()["id"]]


class TestErrorStatusCodes:
    def test_unknown_resource_is_404(self, client):
        run(client, [Step("get", ["missing"], expect=lambda r: r.status_code == 404)])

    def test_duplicate_resource_is_409(self, client):
        run(
            client,
            [
                Step("create_resource", ["dup"]),
                Step("create_resource", ["dup"], expect=lambda r: r.status_code == 409),
            ],
        )

    def test_promote_unknown_version_is_404(self, client):
        run(
            client,
            [
                Step("create_resource", ["fetch"]),
                Step("promote", ["fetch", 99], expect=lambda r: r.status_code == 404),
            ],
        )

    def test_undeclared_resource_upload_is_400(self, client):
        run(
            client,
            [
                Step("create_resource", ["undeclared"]),
                Step("upload_version", ["undeclared", {"n": 1}], expect=lambda r: r.status_code == 400),
            ],
        )


class TestListRoutes:
    def test_list_resources(self, client):
        run(client, [Step("create_resource", ["fetch"])])

        response = client.list_resources()

        assert response.status_code == 200
        assert [r["name"] for r in response.json()] == ["fetch"]

    def test_list_versions(self, client):
        run(
            client,
            [
                Step("create_resource", ["fetch"]),
                Step("upload_version", ["fetch", {"n": 1}]),
                Step("upload_version", ["fetch", {"n": 2}]),
            ],
        )

        response = client.list_versions("fetch")

        assert response.status_code == 200
        assert [v["version"] for v in response.json()] == [1, 2]

    def test_list_versions_unknown_resource_is_404(self, client):
        response = client.list_versions("does_not_exist")
        assert response.status_code == 404


def test_healthz():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
