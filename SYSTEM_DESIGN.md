# Requirements

Stage Runner is a workflow orchestrator for staged Python workloads. Each **stage** is a unit
of work (a Python function) that consumes and produces **resources** — versioned data
artifacts passed between stages. Stage Runner validates every resource against a schema
before it is promoted, executes stages in dependency order (including fan-out/fan-in — a
stage's dependents can run in parallel once it completes, and a stage with several
dependencies waits for all of them), and can roll back to the last known-good resource
version (automatically on failure via `on_failure="fallback"`, or on demand via the promote
API) — with full visibility into run history via the web UI and CLI.

## Functional

1. Users define stage workloads as Python functions, declaring name, dependencies (own
   `retries` count) and registering into a workflow's `StageRegistry`.
2. Each resource a stage produces is validated against its declared schema (`resources/<name>.py`)
   before being promoted to "current"; a resource with no declared contract can't be uploaded
   to at all.
3. The Scheduler executes stages in DAG order, dispatching each dispatchable stage's workload
   in its own isolated container (Docker-out-of-Docker from the Runner). Multiple stages ready
   at once dispatch together; a stage isn't dispatched until every one of its dependencies is.
4. On stage failure (execution error, exhausted retries, or output validation failure), the
   workflow's `on_failure` policy decides what happens: `"halt"` (default) stops the run;
   `"fallback"` continues, treating the failed stage as if it had produced its
   currently-promoted resource version instead (recorded as `used_fallback` on that stage's
   run, so it stays visible that the run built on a stale value). A per-run request can
   override either way. `retries` (per stage) covers transient failures separately, before a
   stage is even considered to have failed.
5. Operators can manually promote a resource to an older version (rollback) via the API, CLI,
   or web UI, or inject any resource version directly (`resource upload`), including
   deliberately invalid ones, to test failure/rollback paths without touching real inputs.
6. Runs can be triggered once (immediately or at a future time), or on a recurring cadence
   (cron or a fixed interval in seconds); an in-flight run, a not-yet-dispatched one-off
   schedule, or a recurring schedule's standing rule can each be cancelled independently.

## Non-functional

1. **Reproducibility** — the full system (four services, Postgres, Redis, MinIO, the web UI)
   runs via `docker compose up --build -d` on a clean machine.
2. **Simplicity over completeness** — sequential DAG execution was the original baseline;
   fan-out/fan-in dispatch (multiple ready stages at once, a stage waiting on several
   dependencies) is now core, not a stretch goal, since it costs nothing extra in the
   dispatch loop's own design once the graph itself isn't assumed to be a chain.
3. **Testability** — three layers, each catching what the one below it can't (see
   "Tests" in `README.md` for how to run each): unit tests exercise one service's logic
   against in-memory fakes, no Docker required; integration tests exercise the real
   Postgres-backed repositories against an ephemeral Postgres (`testcontainers`), catching
   wrong SQL a fake can't; system tests drive the actual running stack end to end over HTTP,
   with the checked-in `workflows/feed_*` packages doing double duty as both live demo
   fixtures and what those system tests trigger, each exercising one specific behavior
   (happy path, crash, timeout, validation failure, fallback, branching).
4. **Auditability** — every resource version and stage run is retained (append-only), so a
   failure, retry, or fallback is explainable after the fact from the run's own record, not
   just from logs.

**Out of scope:** distributed/multi-node scheduling, authn/authz, multi-tenant isolation,
non-Python workloads, metrics/alerting (no Prometheus/Grafana/Alertmanager — run history and
status are inspected live via the web UI/API instead).

# Core Schemas & API

## Resource Store

Owns its own Postgres database (`resource_store`) and MinIO bucket. The only service that
ever touches blob storage or resource metadata directly.

resources
- id, name, current_version_id

resource_versions
- id, resource_id, name, version, storage_uri, created_at, is_test, validation_error

resource_version_dependencies
- version_id, depends_on_id (recorded by the Runner after a successful upload: which
  upstream versions this one was actually computed from)

API
- GET /resources
- POST /resources/{name}/versions
- PUT /resources/{name}/versions/{version}/dependencies
- POST /resources/{name}/promotions
- GET /resources/{name}
- GET /resources/{name}/versions
- GET /resources/{name}/versions/{version}
- GET /resources/{name}/versions/{version}/dependencies

## Workflow Service

Owns its own Postgres database (`workflow_service`). Client-facing intake only — it records
intent and proxies status; it never dispatches anything. The Scheduler reads/writes this same
database directly (not through this API) for everything past intake.

runs (WorkflowRun)
- id, workflow_name, start_from, stop_after, input_versions, promote, status, requested_at,
  started_at, finished_at, error, cancel_requested, on_failure

stage_runs (StageRun)
- id, workflow_run_id, workflow_name, stage_name, input_versions, promote, output_version,
  status, requested_at, started_at, finished_at, error, attempts, used_fallback

schedules (Schedule — a one-off trigger request)
- id, workflow_name, start_from, stop_after, input_versions, promote, requested_at, run_at,
  dispatched_at, run_id, on_failure, cancel_requested

recurring_schedules (RecurringSchedule — a standing rule, never itself "dispatched"; each
firing spawns a plain `runs` row via the same defaults)
- id, workflow_name, start_from, stop_after, input_versions, promote, enabled, next_run_at,
  created_at, cron_expression, interval_seconds, on_failure
  (exactly one of cron_expression/interval_seconds is set)

API
- GET /workflows
- GET /workflows/{name}/stages
- POST /workflows/{name}/runs
- GET /workflows/{name}/schedules
- GET /workflows/{name}/schedules/{schedule_id}
- POST /workflows/{name}/schedules/{schedule_id}/cancel
- POST /workflows/{name}/recurring-schedules
- GET /workflows/{name}/recurring-schedules
- POST /workflows/{name}/recurring-schedules/{id}/cancel
- GET /workflows/{name}/runs
- GET /workflows/{name}/runs/{run_id}
- POST /workflows/{name}/runs/{run_id}/cancel
- GET /workflows/{name}/runs/{run_id}/stage-runs
- GET /workflows/{name}/stage-runs/{stage_run_id}
- POST /workflows/{name}/stage-runs/{stage_run_id}/start
- POST /workflows/{name}/stage-runs/{stage_run_id}/complete
- POST /workflows/{name}/stage-runs/{stage_run_id}/fail (worker-facing; the last three are
  called by the Runner, not by an end client)

## Scheduler

No client-facing API — an internal poller with no HTTP surface, ticking every
`POLL_INTERVAL_SECONDS` against the Workflow Service's own Postgres database. Three phases,
all re-run every tick:
1. **recurring intake** — for every enabled `recurring_schedules` row whose `next_run_at` has
   arrived, spawn a plain `runs` row with that row's defaults and advance `next_run_at` (via
   croniter for `cron_expression`, or `now + interval_seconds`).
2. **intake** — drain undispatched, non-cancelled `schedules` into a `runs` row.
3. **progression** — for every active `runs` row: honor `cancel_requested` (mark cancelled,
   dispatch nothing further); otherwise walk the workflow's DAG and dispatch every stage
   whose dependencies are all done and hasn't itself been dispatched yet (this is what lets
   independent branches fire in the same tick, and holds a fan-in stage back until every
   dependency is). A failed stage triggers `on_failure`: `"fallback"` resolves it to its
   currently-promoted version and marks that stage's run `used_fallback`, letting the run
   continue; otherwise the whole run is marked failed.

Redis message (list `stagerunner:stage_runs`, LPUSH/BRPOP)
- stage_run_id, workflow_run_id, workflow_name, stage_name, input_versions, promote

## Runner

Also no client-facing API — a Redis consumer (BRPOP on `stagerunner:stage_runs`). Executes
exactly one stage per dispatch: resolves its Python function via the workflow's own
`StageRegistry`, runs it in a fresh sibling container (Docker-out-of-Docker; the container
image is `runner`'s own), retries up to the stage's declared `retries` on failure, uploads a
new resource version on success, and calls back into workflow_service's
start/complete/fail endpoints to report progress.

# Timeline

Implemented, roughly in this order: Resource Store → stage definition API → Scheduler →
failure injection + manual rollback (CLI and web UI) → containerized per-stage execution →
stage retries → per-run `on_failure` override + fallback visibility → one-off and recurring
(cron and fixed-interval) scheduling, with cancellation at every level → branching DAG support
→ web UI (Dashboard, Workflows/Resources lists and detail pages, a static structure graph).

# Components

See "Architecture" in `README.md` for the current service diagram and a one-paragraph
description of each service's responsibility.

# Deep Dive

Design decisions and their rationale live as docstrings/comments in the code itself, close to
what they explain — e.g. `services/scheduler/src/poller.py`'s module docstring for the
dispatch loop and `on_failure` resolution, `lib/stages.py` for `StageRegistry`/`retries`, and
each `workflows/feed_*/__init__.py` for what that particular example demonstrates.
