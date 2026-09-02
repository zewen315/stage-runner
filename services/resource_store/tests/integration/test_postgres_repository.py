"""Integration tests: PostgresMetadataRepository against a real, ephemeral
Postgres (testcontainers), not the InMemoryMetadataRepository fake every
other test in this suite uses. Exists to catch what those tests
structurally can't: the actual SQL being wrong -- a bad column name, a
broken JOIN, a constraint that doesn't do what the code assumes -- none
of which shows up against a fake that just mirrors Python dicts.

Excluded from the default `pytest` run (see pyproject.toml's addopts);
needs Docker. Run explicitly with `uv run pytest -m integration`.
"""

from __future__ import annotations

import pytest
from testcontainers.community.postgres import PostgresContainer

from postgres_repository import PostgresMetadataRepository

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgres:16") as container:
        yield container


@pytest.fixture
def repo(postgres_container):
    # Schema is idempotent CREATE TABLE IF NOT EXISTS, but each test still
    # gets a clean slate -- container is module-scoped (expensive to
    # start), tables are wiped between tests instead.
    dsn = postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
    repository = PostgresMetadataRepository(dsn)
    yield repository
    with repository._conn.cursor() as cur:
        cur.execute("TRUNCATE resource_version_dependencies, resource_versions, resources RESTART IDENTITY CASCADE")
    repository.close()


class TestGetOrCreateResource:
    def test_creates_a_new_resource(self, repo):
        resource = repo.get_or_create_resource("raw_events")
        assert resource.name == "raw_events"
        assert resource.current_version_id is None

    def test_is_idempotent_for_an_existing_name(self, repo):
        first = repo.get_or_create_resource("raw_events")
        second = repo.get_or_create_resource("raw_events")
        assert first.id == second.id

    def test_get_resource_returns_none_for_unknown_name(self, repo):
        assert repo.get_resource("does_not_exist") is None


class TestVersionsAndPromotion:
    def test_next_version_starts_at_one(self, repo):
        resource = repo.get_or_create_resource("raw_events")
        assert repo.next_version(resource.id) == 1

    def test_next_version_increments_past_recorded_versions(self, repo):
        resource = repo.get_or_create_resource("raw_events")
        repo.record_version(resource.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00")
        assert repo.next_version(resource.id) == 2

    def test_record_and_read_back_a_version(self, repo):
        resource = repo.get_or_create_resource("raw_events")
        recorded = repo.record_version(
            resource.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00", is_test=True
        )

        fetched = repo.get_version(resource.id, 1)

        assert fetched.id == recorded.id
        assert fetched.name == "raw_events"  # joined from resources, not stored on the row itself
        assert fetched.is_test is True
        assert fetched.validation_error is None

    def test_validation_error_is_persisted_not_rejected(self, repo):
        resource = repo.get_or_create_resource("raw_events")
        recorded = repo.record_version(
            resource.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00", validation_error="bad shape"
        )
        assert repo.get_version_by_id(recorded.id).validation_error == "bad shape"

    def test_list_versions_is_ordered_by_version_ascending(self, repo):
        resource = repo.get_or_create_resource("raw_events")
        repo.record_version(resource.id, 2, "raw_events/v2.json", "2026-01-02T00:00:00+00:00")
        repo.record_version(resource.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00")

        versions = repo.list_versions(resource.id)

        assert [v.version for v in versions] == [1, 2]

    def test_promote_updates_current_version_id(self, repo):
        resource = repo.get_or_create_resource("raw_events")
        recorded = repo.record_version(resource.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00")

        repo.promote(resource.id, recorded.id)

        assert repo.get_resource("raw_events").current_version_id == recorded.id


class TestDependencies:
    def test_set_and_get_dependencies(self, repo):
        raw = repo.get_or_create_resource("raw_events")
        raw_v1 = repo.record_version(raw.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00")
        agg = repo.get_or_create_resource("aggregate_signals")
        agg_v1 = repo.record_version(agg.id, 1, "aggregate_signals/v1.json", "2026-01-01T00:00:01+00:00")

        repo.set_dependencies(agg_v1.id, [raw_v1.id])

        assert repo.get_dependencies(agg_v1.id) == [raw_v1.id]

    def test_set_dependencies_replaces_the_previous_set(self, repo):
        raw = repo.get_or_create_resource("raw_events")
        raw_v1 = repo.record_version(raw.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00")
        raw_v2 = repo.record_version(raw.id, 2, "raw_events/v2.json", "2026-01-01T00:00:01+00:00")
        agg = repo.get_or_create_resource("aggregate_signals")
        agg_v1 = repo.record_version(agg.id, 1, "aggregate_signals/v1.json", "2026-01-01T00:00:02+00:00")

        repo.set_dependencies(agg_v1.id, [raw_v1.id])
        repo.set_dependencies(agg_v1.id, [raw_v2.id])

        assert repo.get_dependencies(agg_v1.id) == [raw_v2.id]

    def test_no_dependencies_returns_empty_list(self, repo):
        raw = repo.get_or_create_resource("raw_events")
        raw_v1 = repo.record_version(raw.id, 1, "raw_events/v1.json", "2026-01-01T00:00:00+00:00")
        assert repo.get_dependencies(raw_v1.id) == []


def test_schema_survives_being_initialized_twice(postgres_container):
    """Two services (or two test runs) both call CREATE TABLE IF NOT
    EXISTS against the same database on startup -- must be a no-op the
    second time, not an error."""
    dsn = postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
    first = PostgresMetadataRepository(dsn)
    second = PostgresMetadataRepository(dsn)
    first.close()
    second.close()
