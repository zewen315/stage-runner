"""Postgres-backed MetadataRepository.

Mirrors InMemoryMetadataRepository's behavior exactly (see memory.py) --
same three concepts (resources, resource_versions, dependency edges), just
persisted. `resource_versions` has no `status`/promotions-log columns; we
dropped that machinery when trimming the service down to its four core
operations, and the schema follows the code.
"""

from __future__ import annotations

import psycopg

from errors import ResourceAlreadyExistsError, ResourceNotFoundError
from models import Resource, ResourceVersion

_SCHEMA = """
CREATE TABLE IF NOT EXISTS resources (
    id                  BIGSERIAL PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    -- No FK to resource_versions here: resources and resource_versions
    -- reference each other (a resource's current version, a version's
    -- resource), and Postgres has no idempotent "ADD CONSTRAINT IF NOT
    -- EXISTS" to break that cycle safely on every schema-init run. Kept as
    -- an application-enforced invariant instead (see promote()).
    current_version_id  BIGINT
);

CREATE TABLE IF NOT EXISTS resource_versions (
    id           BIGSERIAL PRIMARY KEY,
    resource_id  BIGINT NOT NULL REFERENCES resources (id),
    version      INTEGER NOT NULL CHECK (version > 0),
    storage_uri  TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    UNIQUE (resource_id, version)
);

CREATE TABLE IF NOT EXISTS resource_version_dependencies (
    version_id     BIGINT NOT NULL REFERENCES resource_versions (id),
    depends_on_id  BIGINT NOT NULL REFERENCES resource_versions (id),
    PRIMARY KEY (version_id, depends_on_id)
);
"""


class PostgresMetadataRepository:
    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def create_resource(self, name: str) -> Resource:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO resources (name) VALUES (%s) RETURNING id, name, current_version_id",
                    (name,),
                )
                row = cur.fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise ResourceAlreadyExistsError(f"resource {name!r} already exists") from exc

        return Resource(id=row[0], name=row[1], current_version_id=row[2])

    def get_resource(self, name: str) -> Resource | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, current_version_id FROM resources WHERE name = %s", (name,)
            )
            row = cur.fetchone()
        return Resource(id=row[0], name=row[1], current_version_id=row[2]) if row else None

    def next_version(self, resource_id: int) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM resource_versions WHERE resource_id = %s",
                (resource_id,),
            )
            return cur.fetchone()[0]

    def record_version(
        self, resource_id: int, version: int, storage_uri: str, created_at: str
    ) -> ResourceVersion:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO resource_versions (resource_id, version, storage_uri, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (resource_id, version, storage_uri, created_at),
            )
            version_id = cur.fetchone()[0]

        return ResourceVersion(
            id=version_id,
            resource_id=resource_id,
            version=version,
            storage_uri=storage_uri,
            created_at=created_at,
        )

    def get_version(self, resource_id: int, version: int) -> ResourceVersion | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, resource_id, version, storage_uri, created_at
                FROM resource_versions WHERE resource_id = %s AND version = %s
                """,
                (resource_id, version),
            )
            row = cur.fetchone()
        return self._version_from_row(row) if row else None

    def get_version_by_id(self, version_id: int) -> ResourceVersion | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, resource_id, version, storage_uri, created_at
                FROM resource_versions WHERE id = %s
                """,
                (version_id,),
            )
            row = cur.fetchone()
        return self._version_from_row(row) if row else None

    @staticmethod
    def _version_from_row(row) -> ResourceVersion:
        return ResourceVersion(
            id=row[0],
            resource_id=row[1],
            version=row[2],
            storage_uri=row[3],
            created_at=row[4].isoformat(),
        )

    def set_dependencies(self, version_id: int, depends_on_ids: list[int]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM resource_version_dependencies WHERE version_id = %s", (version_id,)
            )
            cur.executemany(
                "INSERT INTO resource_version_dependencies (version_id, depends_on_id) VALUES (%s, %s)",
                [(version_id, depends_on_id) for depends_on_id in depends_on_ids],
            )

    def get_dependencies(self, version_id: int) -> list[int]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT depends_on_id FROM resource_version_dependencies WHERE version_id = %s",
                (version_id,),
            )
            return [row[0] for row in cur.fetchall()]

    def promote(self, resource_id: int, version_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE resources SET current_version_id = %s WHERE id = %s",
                (version_id, resource_id),
            )
