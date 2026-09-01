"""Scheduler: the only thing that decides what runs next.

Two phases, both re-run every tick:
- intake: drain undispatched `schedules` into a `WorkflowRun` (never
  queued, pure tracking). `promote` resolves here if the caller didn't
  specify one: true only for a full run (`start_from` and `stop_after`
  both unset), false for any partial one.
- progression: for every in-flight `WorkflowRun`, dispatch a `StageRun`
  for each *reachable* stage whose dependencies are all complete.
  `start_from`/`stop_after` narrow a run to a sub-range of the DAG: when
  `start_from` is set, only it and stages that transitively depend on it
  are ever dispatched (`dag.reachable_from`) -- everything upstream is
  skipped entirely, with `input_versions` supplying whatever `start_from`
  itself needs that this run won't produce. Once `stop_after` (if set) is
  `completed`, the run finishes immediately, even if other
  reachable-but-undispatched stages remain. A worker never sees more than
  one stage; DAG order and range lives here, not in the Runner.

A workflow whose registry declares `on_failure="fallback"` doesn't halt when
a stage fails -- the Scheduler treats it as if that stage had produced its
currently-promoted resource version instead (same `input_versions`-pinning
mechanism `start_from` already uses), and keeps dispatching downstream.
That's the one thing here that reaches outside this service's own Postgres
DB and Redis: resolving "currently-promoted" means asking resource_store,
via the same `ResourceClient` the Runner already uses.

`poll_once` takes its collaborators (a ScheduleStore, a RunQueue, a
registry_provider for loading a workflow's StageRegistry, and a
ResourceClient) as parameters rather than constructing them, so it's
testable with the in-memory fakes in memory.py/lib -- no real Postgres,
Redis, resource_store, or filesystem needed for tests/test_poller.py.
`main` is the thin, untested wiring that builds the real versions and runs
the poll loop.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable

from dag import UnknownDependencyError, reachable_from, topological_order
from resource_store_client import ResourceClient
from stages import StageRegistry

from ports import RunQueue, ScheduleStore

RegistryProvider = Callable[[str], StageRegistry]


def poll_once(
    store: ScheduleStore, queue: RunQueue, registry_provider: RegistryProvider, resources: ResourceClient
) -> None:
    _intake(store, queue)
    _progress(store, queue, registry_provider, resources)


def _resolve_promote(promote: bool | None, start_from: str | None, stop_after: str | None) -> bool:
    if promote is not None:
        return promote
    return start_from is None and stop_after is None


def _intake(store: ScheduleStore, queue: RunQueue) -> None:
    for schedule in store.pending_schedules():
        promote = _resolve_promote(schedule.promote, schedule.start_from, schedule.stop_after)
        run_id = store.create_workflow_run(
            schedule.workflow_name,
            schedule.start_from,
            schedule.stop_after,
            schedule.input_versions,
            promote,
        )
        store.mark_schedule_dispatched(schedule.id, run_id=run_id)


def _progress(
    store: ScheduleStore, queue: RunQueue, registry_provider: RegistryProvider, resources: ResourceClient
) -> None:
    for run in store.active_workflow_runs():
        try:
            registry = registry_provider(run.workflow_name)
            order = topological_order(registry.all())
        except Exception as exc:  # noqa: BLE001 -- a bad/unloadable DAG fails the run, not the poller
            store.mark_workflow_run_failed(run.id, error=str(exc))
            continue

        by_name = {s.name: s for s in order}

        try:
            reachable = reachable_from(order, run.start_from) if run.start_from else set(by_name)
        except UnknownDependencyError as exc:
            store.mark_workflow_run_failed(run.id, error=str(exc))
            continue

        if run.stop_after is not None and run.stop_after not in by_name:
            store.mark_workflow_run_failed(run.id, error=f"unknown stop_after stage {run.stop_after!r}")
            continue
        if run.stop_after is not None and run.stop_after not in reachable:
            store.mark_workflow_run_failed(
                run.id,
                error=f"stop_after={run.stop_after!r} is not reachable from start_from={run.start_from!r}",
            )
            continue

        if run.start_from is not None:
            missing = [
                dep for dep in by_name[run.start_from].depends_on if dep not in (run.input_versions or {})
            ]
            if missing:
                store.mark_workflow_run_failed(
                    run.id, error=f"start_from={run.start_from!r} missing input_versions for {missing}"
                )
                continue

        stage_runs = store.stage_runs_for_workflow_run(run.id)
        started = {sr.stage_name for sr in stage_runs}
        done = {sr.stage_name: sr.output_version for sr in stage_runs if sr.status == "completed"}
        failed = [sr for sr in stage_runs if sr.status == "failed"]

        if failed:
            failure = failed[0]
            fell_back = False
            if registry.on_failure == "fallback":
                try:
                    fallback_version, _ = resources.get(failure.stage_name)
                except Exception:  # noqa: BLE001 -- no current version, store unreachable, etc.
                    fallback_version = None
                if fallback_version is not None:
                    done[failure.stage_name] = fallback_version
                    fell_back = True
            if not fell_back:
                store.mark_workflow_run_failed(run.id, error=f"{failure.stage_name}: {failure.error}")
                continue

        if run.stop_after is not None and run.stop_after in done:
            store.mark_workflow_run_completed(run.id)
            continue

        if run.start_from is not None:
            done.update(run.input_versions or {})

        dispatched_any = False
        for stage_def in order:
            if stage_def.name not in reachable or stage_def.name in started:
                continue
            if all(dep in done for dep in stage_def.depends_on):
                input_versions = {dep: done[dep] for dep in stage_def.depends_on}
                stage_run_id = store.create_stage_run(
                    workflow_run_id=run.id,
                    workflow_name=run.workflow_name,
                    stage_name=stage_def.name,
                    input_versions=input_versions,
                    promote=run.promote,
                )
                queue.enqueue_stage_run(
                    stage_run_id, run.id, run.workflow_name, stage_def.name, input_versions, run.promote
                )
                started.add(stage_def.name)
                dispatched_any = True

        if dispatched_any and run.status == "requested":
            store.mark_workflow_run_running(run.id)

        if reachable <= done.keys():
            store.mark_workflow_run_completed(run.id)


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    resource_store_url = os.environ["RESOURCE_STORE_URL"]
    workflows_root = Path(os.environ.get("WORKFLOWS_ROOT", "/workflows"))
    poll_interval = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))

    from postgres_store import PostgresScheduleStore
    from redis_queue import RedisRunQueue
    from resource_store_client import HttpResourceClient
    from workflow_loader import load_workflow

    store = PostgresScheduleStore(database_url)
    queue = RedisRunQueue(redis_url)
    resources = HttpResourceClient(resource_store_url)

    def registry_provider(workflow_name: str) -> StageRegistry:
        return load_workflow(workflows_root / workflow_name)

    print(f"scheduler polling every {poll_interval}s...", flush=True)
    while True:
        try:
            poll_once(store, queue, registry_provider, resources)
        except Exception as exc:  # noqa: BLE001 -- one bad tick shouldn't kill the poller
            print(f"poll error: {exc}", file=sys.stderr, flush=True)
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
