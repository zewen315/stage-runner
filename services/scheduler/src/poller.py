"""Scheduler: the only thing that decides what runs next.

Two phases, both re-run every tick:
- intake: drain undispatched `schedules` -- a workflow-scoped one becomes a
  `WorkflowRun` (never queued, pure tracking); a stage-scoped one becomes a
  standalone `StageRun`, dispatched immediately.
- progression: for every in-flight `WorkflowRun`, dispatch a `StageRun` for
  each stage whose dependencies are all complete, pinning its inputs to
  *this run's own* completed upstream outputs (never "current" -- see
  the design notes in the plan this implements). A worker never sees more
  than one stage; DAG order lives here, not in the Runner.

`poll_once` takes its collaborators (a ScheduleStore, a RunQueue, and a
registry_provider for loading a workflow's StageRegistry) as parameters
rather than constructing them, so it's testable with the in-memory fakes in
memory.py -- no real Postgres, Redis, or filesystem needed for
tests/test_poller.py. `main` is the thin, untested wiring that builds the
real versions and runs the poll loop.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable

from dag import topological_order
from stages import StageRegistry

from ports import RunQueue, ScheduleStore

RegistryProvider = Callable[[str], StageRegistry]


def poll_once(store: ScheduleStore, queue: RunQueue, registry_provider: RegistryProvider) -> None:
    _intake(store, queue)
    _progress(store, queue, registry_provider)


def _intake(store: ScheduleStore, queue: RunQueue) -> None:
    for schedule in store.pending_schedules():
        if schedule.scope == "workflow":
            run_id = store.create_workflow_run(schedule.workflow_name)
            store.mark_schedule_dispatched(schedule.id, run_id=run_id)
            continue

        input_versions = schedule.input_versions or {}
        promote = bool(schedule.promote)
        stage_run_id = store.create_stage_run(
            workflow_run_id=None,
            workflow_name=schedule.workflow_name,
            stage_name=schedule.stage_name,
            input_versions=input_versions,
            promote=promote,
        )
        store.mark_schedule_dispatched(schedule.id, stage_run_id=stage_run_id)
        queue.enqueue_stage_run(
            stage_run_id, None, schedule.workflow_name, schedule.stage_name, input_versions, promote
        )


def _progress(store: ScheduleStore, queue: RunQueue, registry_provider: RegistryProvider) -> None:
    for run in store.active_workflow_runs():
        try:
            stage_defs = topological_order(registry_provider(run.workflow_name).all())
        except Exception as exc:  # noqa: BLE001 -- a bad/unloadable DAG fails the run, not the poller
            store.mark_workflow_run_failed(run.id, error=str(exc))
            continue

        stage_runs = store.stage_runs_for_workflow_run(run.id)
        started = {sr.stage_name for sr in stage_runs}
        done = {sr.stage_name: sr.output_version for sr in stage_runs if sr.status == "completed"}
        failed = [sr for sr in stage_runs if sr.status == "failed"]

        if failed:
            failure = failed[0]
            store.mark_workflow_run_failed(run.id, error=f"{failure.stage_name}: {failure.error}")
            continue

        dispatched_any = False
        for stage_def in stage_defs:
            if stage_def.name in started:
                continue
            if all(dep in done for dep in stage_def.depends_on):
                input_versions = {dep: done[dep] for dep in stage_def.depends_on}
                stage_run_id = store.create_stage_run(
                    workflow_run_id=run.id,
                    workflow_name=run.workflow_name,
                    stage_name=stage_def.name,
                    input_versions=input_versions,
                    promote=True,
                )
                queue.enqueue_stage_run(
                    stage_run_id, run.id, run.workflow_name, stage_def.name, input_versions, True
                )
                started.add(stage_def.name)
                dispatched_any = True

        if dispatched_any and run.status == "requested":
            store.mark_workflow_run_running(run.id)

        if done.keys() == {s.name for s in stage_defs}:
            store.mark_workflow_run_completed(run.id)


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    workflows_root = Path(os.environ.get("WORKFLOWS_ROOT", "/workflows"))
    poll_interval = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))

    from postgres_store import PostgresScheduleStore
    from redis_queue import RedisRunQueue
    from workflow_loader import load_workflow

    store = PostgresScheduleStore(database_url)
    queue = RedisRunQueue(redis_url)

    def registry_provider(workflow_name: str) -> StageRegistry:
        return load_workflow(workflows_root / workflow_name)

    print(f"scheduler polling every {poll_interval}s...", flush=True)
    while True:
        try:
            poll_once(store, queue, registry_provider)
        except Exception as exc:  # noqa: BLE001 -- one bad tick shouldn't kill the poller
            print(f"poll error: {exc}", file=sys.stderr, flush=True)
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
