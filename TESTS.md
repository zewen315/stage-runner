# Tests

Three layers, each catching what the one below it structurally can't.

## 1. Unit

One service's own logic in isolation, against in-memory fakes (see each service's
`ports.py`/`memory.py` for the Protocol/fake pattern). No Docker, no network, no real
database — runs in milliseconds.

```
cd services/<resource_store|workflow_service|scheduler|runner> && uv run pytest
cd cli && uv run pytest
cd services/web && npm test          # pure logic only -- DAG layout, pagination
```

| Suite | Tests |
|---|---|
| `services/resource_store` | 29 |
| `services/workflow_service` | 98 |
| `services/scheduler` | 40 |
| `services/runner` (includes `lib/stages.py`, `lib/workflow_loader.py`, `lib/dag.py`) | 46 |
| `cli` | 35 |
| `services/web` | 14 |
| **Total** | **262** |

`services/runner`'s suite also covers the two shared `lib/` modules directly, not just
indirectly through other services' tests: `StageRegistry`/`StageDef` (registration,
`retries`, `on_failure` defaults) and `load_workflow` (including its error paths — a
missing or wrong-typed `registry`, which nothing else exercised).

## 2. Integration

The real Postgres-backed repository classes against an actual, ephemeral Postgres (spun
up per test module via `testcontainers`), instead of the in-memory fakes the unit tests
use for the same interfaces. Exists to catch what a fake structurally can't: a wrong
column name, a broken JOIN, a schema migration that doesn't match the code, an
eligibility predicate (e.g. `pending_schedules`' `AND NOT cancel_requested`) that's
subtly wrong.

Needs Docker. Marked `@pytest.mark.integration` and excluded from the default `pytest`
run in each service's `pyproject.toml` (`addopts = "-m 'not integration'"`), so the fast
unit suites above never need Docker. Run explicitly:

```
cd services/<resource_store|workflow_service|scheduler> && uv run pytest -m integration
```

| Suite | Tests | Covers |
|---|---|---|
| `services/resource_store` | 13 | `PostgresMetadataRepository` |
| `services/workflow_service` | 13 | `PostgresScheduleRepository`, `PostgresRecurringScheduleRepository`, `PostgresWorkflowRunRepository`, `PostgresStageRunRepository` |
| `services/scheduler` | 17 | `PostgresScheduleStore` |
| **Total** | **43** | |

`runner` has no integration suite of its own — it has no Postgres-backed repository; its
one real adapter (`HttpResourceClient`, a thin `httpx` wrapper) is exercised by the system
tests below instead, against the real `resource-store` over HTTP.

## 3. System

The whole stack, actually running, driven entirely over HTTP — the same interface the CLI
and web UI use. Nothing mocked, nothing in-process, no fakes anywhere in the path.

Requires the stack already up:

```
docker compose up --build -d
cd system_tests && uv run pytest
```

If the stack isn't reachable at `http://localhost:8080`, the whole session skips with a
message telling you to start it, rather than every test failing with a confusing
connection error (see `system_tests/conftest.py`'s `client` fixture).

Slow by nature: the checked-in demo workflows each sleep 10s per stage (so the
Scheduler's dispatch is visible live to a human watching `docker compose logs`) — a full
run is 30-40s+, and this suite runs several. That's expected for this layer; it's meant
to run less often than the two above, not on every change. The full suite takes about
3 minutes.

| Scenario | What it proves |
|---|---|
| `TestHappyPath::test_full_run_completes_and_promotes_every_stage` | A full `feed_success` run dispatches every stage in order and promotes each one's output. |
| `TestBranching::test_parallel_branches_dispatch_together_and_fan_in` | `feed_branching`'s two independent stages dispatch in the same Scheduler tick; the fan-in stage waits for both. |
| `TestOnFailureFallback::test_fallback_override_lets_a_halt_by_default_workflow_continue` | A per-run `on_failure=fallback` override makes a halt-by-default workflow (`feed_crash`) continue past a failed stage, marked `used_fallback`. |
| `TestOnFailureFallback::test_halt_override_stops_a_fallback_by_default_workflow` | The reverse override: `on_failure=halt` stops a fallback-by-default workflow (`feed_fallback`) instead. |
| `TestCancellation::test_cancelling_a_run_stops_further_dispatch` | Cancelling an in-flight run stops new stages from dispatching (one already running still finishes in the background). |
| `TestCancellation::test_cancelling_a_pending_schedule_before_it_dispatches` | A one-off schedule cancelled before the Scheduler ever sees it never turns into a run. |
| `TestRecurringSchedule::test_interval_schedule_fires_and_stops_after_cancel` | An interval-based recurring schedule actually fires on its cadence, then stops firing once cancelled. |

**7 scenarios**, all currently passing (full suite: 192.80s).

## Running everything

```
# fast, no Docker
for d in services/resource_store services/workflow_service services/scheduler services/runner cli; do
  (cd "$d" && uv run pytest -q)
done
(cd services/web && npm test)

# needs Docker, spins up ephemeral Postgres containers
for d in services/resource_store services/workflow_service services/scheduler; do
  (cd "$d" && uv run pytest -m integration -q)
done

# needs the real stack already running
docker compose up --build -d
(cd system_tests && uv run pytest -q)
```

**Grand total: 312 tests** (262 unit + 43 integration + 7 system).
