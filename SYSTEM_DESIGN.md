# Requirements

Stage Runner is a workflow orchestrator for staged Python workloads. Each **stage** is a unit
of work (a Python function) that consumes and produces **resources** — versioned data
artifacts passed between stages. Stage Runner validates every resource against a schema
before it is promoted, executes stages in dependency order, and can roll back to the last
known-good resource version (automatically on failure, or on demand) — with full visibility
into run history via Prometheus/Grafana/Alertmanager.

## Functional

1. Users define stage workloads as Python functions, declaring name, dependencies, and
   input/output resource schemas.
2. Each resource a stage produces is validated against its declared schema before being
   promoted to "current".
3. The scheduler executes stages in dependency order (DAG), running each stage's workload in
   an isolated container.
4. On stage failure (execution error or validation failure), the affected resource is
   automatically rolled back to its last known-good version.
5. Operators can manually trigger rollback of a resource, or manually inject a bad resource
   version to test recovery paths (failure injection).
6. Every run emits metrics (stage duration, pass/fail, rollback events) and can trigger
   alerts on failure/rollback.

## Non-functional

1. **Reproducibility** — the full system (scheduler, resource store, Prometheus, Grafana,
   Alertmanager) runs via `docker compose up` on a clean machine.
2. **Simplicity over completeness** — sequential DAG execution is acceptable; parallel stage
   execution is a stretch goal, not a requirement.
3. **Testability** — core logic (DAG resolution, validation, rollback) is unit-testable
   without Docker; container execution is covered by integration tests.
4. **Auditability** — every resource version and stage run is retained (append-only), so a
   failure or rollback is explainable after the fact.

**Out of scope:** distributed/multi-node scheduling, authn/authz, multi-tenant isolation,
non-Python workloads.

# Core Schemas & API

## Resource Store

resources
- id
- name
- current_version_id

resource_versions
- id
- resource_id
- version
- storage_uri
- created_at

resource_version_dependencies
- version_id
- depends_on_id

API
- POST /resources
- POST /resources/{name}/versions
- PUT /resources/{name}/versions/{version}/dependencies
- POST /resources/{name}/promotions
- GET /resources/{name}
- GET /resources/{name}/versions/{version}
- GET /resources/{name}/versions/{version}/dependencies

## Workflow Service

runs
- id
- workflow_name
- status
- requested_at
- started_at
- finished_at
- error
- dispatched_at (internal — set by the Scheduler once it's pushed the run onto Redis)

schedules
- id
- workflow_name
- cron_expression
- enabled
- next_run_at
- created_at

Both tables live in the Workflow Service's own Postgres database. `POST /runs` and
`POST /schedules` only ever write a row here — the Scheduler is a separate polling service that
reads `runs`/`schedules` directly from this database, dispatches due work to Redis, and the
Runner worker consumes that queue and calls back into the `start`/`complete`/`fail` endpoints.

API
- POST /workflows/{name}/runs
- GET /workflows/{name}/runs/{run_id}
- POST /workflows/{name}/runs/{run_id}/start
- POST /workflows/{name}/runs/{run_id}/complete
- POST /workflows/{name}/runs/{run_id}/fail
- POST /workflows/{name}/schedules
- GET /workflows/{name}/schedules

## Scheduler

No client-facing API — an internal poller with no HTTP surface, ticking every
`POLL_INTERVAL_SECONDS` against the Workflow Service's own Postgres database:
1. reads `schedules` for `enabled` rows with `next_run_at <= now`; for each, inserts a `runs`
   row and advances `next_run_at`
2. reads `runs` for rows with `dispatched_at IS NULL` — covering both one-off runs and cron runs
   just spawned in step 1; for each, pushes onto Redis and sets `dispatched_at`

Redis message (list `stagerunner:runs`)
- run_id
- workflow_name

# Timeline

1. Resource Store
2. Stage definition API
3. Scheduler v1 (in-process)
4. Failure injection + manual rollback CLI
5. Container execution
6. Observability

# Components

# Deep Dive

Design decisions