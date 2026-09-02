# Stage Runner

A workflow orchestrator built around one idea: every stage's input and output is a
**versioned resource**, validated against a declared schema before it's promoted to
"current". A stage that fails never corrupts anything downstream — nothing changes until a
new version passes validation and is explicitly promoted, so rollback is just "the last
promotion still stands."

## Quickstart

Requires [Docker](https://docs.docker.com/get-docker/) and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
(for the CLI). Node.js/npm is only needed if you want to run the web app's own test suite or a
local dev server outside Docker — see "Tests" below; `docker compose up --build` builds the web
app itself, no separate npm install required for that path.

```
docker compose up --build -d
```

This starts Postgres, Redis, MinIO, and five services: `resource-store`, `workflow-service`,
`scheduler`, `runner`, and `gateway` (nginx, serving the web UI and proxying `/resources` and
`/workflows` to their services). Everything goes through the gateway at `http://localhost:8080`
— open it in a browser for the web UI. First startup takes a minute or two while images build;
`docker compose ps` shows when everything's healthy. `docker compose down` stops it (add `-v` to
also drop the Postgres/MinIO volumes, for a clean-slate restart).

Every workflow here starts from `raw_events`, a resource with no stage of its own — it has to
be injected before anything can run:

```
cd cli
uv run python stagerunner.py resource upload raw_events ../seed_data/raw_events.json
uv run python stagerunner.py run feed_success --promote
```

`uv run` installs the CLI's own dependencies on first use, into its own `cli/.venv` — no
separate install step needed. `run` polls until the run finishes and prints its final status.
Watch it happen stage-by-stage with `docker compose logs -f scheduler runner`, or in the web UI
at `/workflows/feed_success`.

## Architecture

```
                    ┌────────────┐
   browser ───────► │  gateway   │
                    │  (nginx)   │
                    └─────┬──────┘
                          │ /resources          /workflows
              ┌───────────┴───────────┐   ┌─────────────┴──────────────┐
              ▼                       │   ▼                            │
     ┌─────────────────┐              │  ┌──────────────────┐          │
     │  resource-store  │◄─────────┐  │  │  workflow-service │          │
     │ (Postgres+MinIO)  │         │  │  │    (Postgres)     │          │
     └─────────────────┘           │  │  └──────────────────┘          │
              ▲                    │  │           ▲                    │
              │ HTTP               │  │           │ same Postgres DB   │
              │                    │  │           ▼                    │
     ┌─────────────────┐           │  │  ┌──────────────────┐          │
     │      runner       │◄────────┴──┘  │     scheduler      │        │
     │ (Redis consumer, │   Redis queue  │  (internal poller,  │        │
     │  one stage per    │◄──────────────│   no HTTP surface)  │        │
     │  dispatch, each in │                └──────────────────┘        │
     │  its own container)│                                            │
     └─────────────────┘                                               │
```

- **resource_store** — the only service that reads/writes blobs (MinIO) and resource
  metadata. Owns validation: a resource with no declared contract (see `resources/`) can't be
  uploaded to at all; a value that fails its contract is still persisted (for inspection) but
  never becomes current.
- **workflow_service** — the client-facing intake API. `POST /workflows/{name}/runs` and the
  recurring/cancel endpoints only ever record intent in Postgres; it never dispatches
  anything itself.
- **scheduler** — an internal poller (no HTTP API) that owns `runs`/`stage_runs` end to end:
  drains `schedules`, fires due recurring schedules, walks each active run's DAG dispatching
  every stage whose dependencies are satisfied, and applies `on_failure` (halt vs. fallback)
  when a stage fails.
- **runner** — a Redis consumer. Each dispatched stage runs its pure Python function in its
  own sibling container (Docker-out-of-Docker), retried up to the stage's declared `retries`,
  then reports back to workflow_service.
- **web** (React + Vite) and **cli** (`cli/stagerunner.py`) are two thin, independent clients
  over the same HTTP API — everything one can do, the other can too.

## Defining a workflow

A workflow is a directory under `workflows/` that exposes a `registry: StageRegistry` from
its `__init__.py`. Each stage is a plain Python function:

```python
# workflows/my_workflow/registry.py
from stages import StageRegistry
registry = StageRegistry()  # or StageRegistry(on_failure="fallback")

# workflows/my_workflow/score_items.py
from .registry import registry

@registry.stage("score_items", depends_on=["aggregate_signals"], retries=2)
def score_items(aggregate_signals: dict) -> dict:
    ...
```

- `depends_on` names other stages (or an external resource with no stage of its own, like
  `raw_events` — see `resources/raw_events.py`) — the DAG is whatever this implies. Multiple
  stages can depend on the same one (fan-out) and a stage can depend on several (fan-in); see
  `workflows/feed_branching` for a working example.
- `retries` (default 0) is extra attempts after the first if the stage raises or its output
  fails validation.
- `StageRegistry(on_failure="fallback")` makes the whole workflow continue past a failed stage
  by treating it as if it had produced its currently-promoted resource version instead
  (visible on that stage's run as `used_fallback`); the default, `"halt"`, stops the run. A
  per-run request can override either way.
- Every resource name a stage reads or writes needs a matching `resources/<name>.py` with a
  `validate(value)` function — with no declared contract, that resource can't be uploaded to
  at all.

`workflows/feed_success` (and its siblings `feed_crash`, `feed_timeout`,
`feed_validation_failed`, `feed_fallback`, `feed_branching`) are worked examples, each
demonstrating one specific behavior.

## Concepts

- **Resources & versions** — every stage's input and output is a named, versioned resource.
  Uploading a version never makes it current by itself; promotion is the separate, explicit
  step (`POST /resources/{name}/promotions`, or the CLI's `resource upload --promote`) that a
  run actually reads.
- **Runs** — `stagerunner run <workflow>` triggers the whole DAG from its natural roots.
  `--stage NAME` runs just one stage; `--start-from`/`--stop-after` narrow to a sub-range.
  `--input NAME=VERSION` pins a dependency the run itself won't produce.
- **Scheduling** — `--at TIMESTAMP` delays a one-off run. `recurring create --cron EXPR` fires
  on a standard cron cadence; `--interval-seconds N` fires every N seconds instead (cron's own
  resolution bottoms out at a minute). Both a one-off schedule (before it's dispatched) and a
  recurring schedule (its standing rule) can be cancelled.
- **Cancellation** — an in-flight run can be asked to stop (`POST .../runs/{id}/cancel`); a
  stage already dispatched to the Runner keeps executing, but nothing further gets dispatched
  after that.
- **Retry & fallback visibility** — a stage's `attempts` (>1 only if it retried) and
  `used_fallback` are recorded on its own StageRun record and surfaced in both the CLI's
  underlying API responses and the web UI, so a run's history stays honest about what it
  actually built on.

## CLI

```
cli/stagerunner.py run <workflow> [--stage NAME | --start-from NAME] [--stop-after NAME]
    [--input RESOURCE=VERSION ...] [--promote] [--at TIMESTAMP]
    [--on-failure {halt,fallback}] [--no-wait]

cli/stagerunner.py resource upload <name> <file> [--promote | --no-promote]

cli/stagerunner.py recurring create <workflow> {--cron EXPR | --interval-seconds N}
    [--stage NAME | --start-from NAME] [--stop-after NAME]
    [--input RESOURCE=VERSION ...] [--promote] [--on-failure {halt,fallback}]
cli/stagerunner.py recurring list <workflow>
cli/stagerunner.py recurring cancel <workflow> <id>
```

Every subcommand takes `--base-url` (default `http://localhost:8080`, the gateway). Run
`cli/stagerunner.py -h` (or `<command> -h`) for the full flag reference — the module docstring
at the top of `cli/stagerunner.py` explains the ideas behind each one in more depth.

## Web UI

- **Dashboard** (`/`) — every workflow's Scheduled, Ongoing, and Finished runs, paginated,
  polling live.
- **Workflows** (`/workflows`) — every workflow and its most recent run; click through to a
  workflow's structure (as a graph or a flat list) and full run history.
- **Resources** (`/resources`) — every resource's current version; click through to its full
  version history, each with a **Promote** button (the same manual-rollback path the API has
  always supported).
- A run, schedule, or recurring schedule's own detail page shows its full state and, where it
  makes sense, a Stop/Cancel action.

## Project layout

```
lib/                shared code: stages.py (StageRegistry), dag.py, resource_store_client.py,
                     workflow_loader.py -- imported by whichever service needs it
services/
  resource_store/    versioned resource metadata + blob storage
  workflow_service/  client-facing intake API
  scheduler/         internal poller/dispatcher
  runner/            Redis consumer, executes one stage per dispatch
  web/               React + Vite operate console
cli/                 stagerunner.py -- thin HTTP client, same surface as the web UI
workflows/           workflow definitions (see "Defining a workflow" above)
resources/           declared contracts, one file per resource name
gateway/             nginx: serves the built web app, proxies /resources and /workflows
seed_data/           sample raw_events.json for the quickstart
system_tests/        end-to-end tests against the real, running stack (see "Tests" below)
```

## Tests

Three layers, each catching what the one below it structurally can't.

**Unit** — one service's own logic in isolation, against in-memory fakes (see each
service's `ports.py`/`memory.py`). No Docker, no network, runs in milliseconds. `uv run`
installs each Python service's own dependencies on first use (a separate `.venv` per
service); the web app needs an explicit `npm install` first (only `uv run` auto-installs):

```
cd services/<resource_store|workflow_service|scheduler|runner> && uv run pytest
cd cli && uv run pytest
cd services/web && npm install && npm test   # pure logic only -- DAG layout, pagination
```

**Integration** — the real Postgres-backed repository classes against an actual,
ephemeral Postgres (via `testcontainers`, one per test module), instead of the in-memory
fakes the unit tests use for the same interfaces. Catches what a fake can't: wrong SQL, a
bad column name, a migration that doesn't match the code. Needs Docker; excluded from the
default `pytest` run, so it never slows down the unit suite above:

```
cd services/<resource_store|workflow_service|scheduler> && uv run pytest -m integration
```

**System** — the whole stack, actually running, driven entirely over HTTP (the same
interface the CLI and web UI use) — nothing mocked, nothing in-process. Each test mirrors
a behavior from "Concepts" above: a full run promoting every stage, a branching workflow's
parallel dispatch and fan-in, an `on_failure` override, cancelling a run vs. a pending
schedule, a recurring schedule firing and being cancelled. Needs the stack already running
(`docker compose up --build -d` first — the suite skips with a clear message otherwise) and
is slow by nature (the demo workflows each sleep 10s per stage, for the same reason the
Scheduler's dispatch is visible live in `docker compose logs`) — this layer runs less often
than the two above, not on every change:

```
cd system_tests && uv run pytest
```
