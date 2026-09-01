"""Usage:
  uv run python cli/stagerunner.py run <workflow-name>
      [--stage NAME | --start-from NAME] [--stop-after NAME]
      [--input <resource>=<version> ...] [--promote]
      [--base-url URL] [--no-wait]

Thin client: this only ever talks HTTP to the Workflow Service (through the
gateway, by default). It requests a trigger and optionally polls for its
outcome -- it has no DAG/execution logic of its own, no knowledge of the
Resource Store, and no dependency on the Scheduler's or Runner's
internals. A request only ever creates a `schedules` row; actually
dispatching and running it happens elsewhere, asynchronously: the
Scheduler drains `schedules` and dispatches stage-by-stage, and the Runner
worker executes exactly one stage per dispatch.

Every run is a WorkflowRun -- `--stage`/`--start-from`/`--stop-after`
narrow it to a sub-range of the workflow's DAG rather than naming a
different kind of thing. Plain `run <workflow>` runs the whole DAG.
`--stage NAME` is sugar for `--start-from NAME --stop-after NAME` (run
just that one stage). `--start-from NAME` alone resumes the rest of the
pipeline from that stage onward. `--stop-after NAME` alone runs from the
natural roots and stops once that stage completes.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def _parse_input(raw: str) -> tuple[str, int]:
    name, _, version = raw.partition("=")
    if not version:
        raise argparse.ArgumentTypeError(f"expected <resource>=<version>, got {raw!r}")
    return name, int(version)


def _poll_schedule(client: httpx.Client, workflow: str, schedule_id: int, *, no_wait: bool) -> int:
    response = client.get(f"/workflows/{workflow}/schedules/{schedule_id}")
    response.raise_for_status()
    schedule = response.json()
    print(f"requested schedule {schedule['id']} for {workflow!r} (status={schedule['status']})")

    if no_wait:
        return 0

    while schedule["status"] in ("requested", "running"):
        time.sleep(0.5)
        response = client.get(f"/workflows/{workflow}/schedules/{schedule_id}")
        response.raise_for_status()
        schedule = response.json()

    print(f"run {schedule['run_id']}: {schedule['status']}")
    if schedule["status"] == "failed":
        print(f"error: {schedule['error']}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stagerunner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Trigger a run, once")
    run_parser.add_argument("workflow", help="workflow name, e.g. feed_success")
    run_parser.add_argument(
        "--stage", metavar="NAME", help="run just this one stage (sugar for --start-from/--stop-after NAME)"
    )
    run_parser.add_argument(
        "--start-from", metavar="NAME", help="start here instead of the workflow's natural roots"
    )
    run_parser.add_argument("--stop-after", metavar="NAME", help="stop once this stage completes")
    run_parser.add_argument(
        "--input",
        action="append",
        default=[],
        type=_parse_input,
        metavar="RESOURCE=VERSION",
        dest="input_versions",
        help="pin a dependency the run won't itself produce (needed by --start-from/--stage); repeatable",
    )
    run_parser.add_argument(
        "--promote",
        action="store_true",
        help="make produced versions current (default: true for a full run, false for a partial one)",
    )
    run_parser.add_argument("--base-url", default="http://localhost:8080", help="API gateway base URL")
    run_parser.add_argument(
        "--no-wait", action="store_true", help="Request the run and return immediately"
    )

    args = parser.parse_args(argv)

    if args.stage is not None and (args.start_from is not None or args.stop_after is not None):
        parser.error("--stage cannot be combined with --start-from/--stop-after")

    start_from = args.stage or args.start_from
    stop_after = args.stage or args.stop_after

    body: dict = {}
    if start_from is not None:
        body["start_from"] = start_from
    if stop_after is not None:
        body["stop_after"] = stop_after
    if args.input_versions:
        body["input_versions"] = dict(args.input_versions)
    if args.promote:
        body["promote"] = True

    client = httpx.Client(base_url=args.base_url)
    response = client.post(f"/workflows/{args.workflow}/runs", json=body)

    if response.status_code == 404:
        print(f"error: no workflow {args.workflow!r}", file=sys.stderr)
        return 1
    response.raise_for_status()
    schedule = response.json()

    return _poll_schedule(client, args.workflow, schedule["id"], no_wait=args.no_wait)


if __name__ == "__main__":
    raise SystemExit(main())
