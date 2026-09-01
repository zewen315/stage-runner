"""Usage:
  uv run python cli/stagerunner.py run <workflow-name> [--base-url URL] [--no-wait]
  uv run python cli/stagerunner.py run-stage <workflow-name> <stage-name>
      [--input <resource>=<version> ...] [--promote] [--base-url URL] [--no-wait]

Thin client: this only ever talks HTTP to the Workflow Service (through the
gateway, by default). It requests a trigger and optionally polls for its
outcome -- it has no DAG/execution logic of its own, no knowledge of the
Resource Store, and no dependency on the Scheduler's or Runner's
internals. A request only ever creates a `schedules` row; actually
dispatching and running it happens elsewhere, asynchronously: the
Scheduler drains `schedules` and dispatches stage-by-stage, and the Runner
worker executes exactly one stage per dispatch.
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

    target = schedule["run_id"] or schedule["stage_run_id"]
    print(f"{'run' if schedule['run_id'] else 'stage run'} {target}: {schedule['status']}")
    if schedule["status"] == "failed":
        print(f"error: {schedule['error']}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stagerunner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Trigger a whole workflow, once")
    run_parser.add_argument("workflow", help="workflow name, e.g. feed_ranking")
    run_parser.add_argument("--base-url", default="http://localhost:8080", help="API gateway base URL")
    run_parser.add_argument(
        "--no-wait", action="store_true", help="Request the run and return immediately"
    )

    stage_parser = subparsers.add_parser(
        "run-stage", help="Trigger a single stage standalone, once -- e.g. against a pinned input"
    )
    stage_parser.add_argument("workflow", help="workflow name, e.g. feed_ranking")
    stage_parser.add_argument("stage", help="stage name within that workflow, e.g. score_items")
    stage_parser.add_argument(
        "--input",
        action="append",
        default=[],
        type=_parse_input,
        metavar="RESOURCE=VERSION",
        help="pin a dependency to a specific version instead of current; repeatable",
    )
    stage_parser.add_argument(
        "--promote", action="store_true", help="make the produced version current (default: no)"
    )
    stage_parser.add_argument("--base-url", default="http://localhost:8080", help="API gateway base URL")
    stage_parser.add_argument(
        "--no-wait", action="store_true", help="Request the stage run and return immediately"
    )

    args = parser.parse_args(argv)
    client = httpx.Client(base_url=args.base_url)

    if args.command == "run":
        response = client.post(f"/workflows/{args.workflow}/runs")
    else:
        response = client.post(
            f"/workflows/{args.workflow}/stages/{args.stage}/runs",
            json={"input_versions": dict(args.input), "promote": args.promote},
        )

    if response.status_code == 404:
        print(f"error: no workflow {args.workflow!r}", file=sys.stderr)
        return 1
    response.raise_for_status()
    schedule = response.json()

    return _poll_schedule(client, args.workflow, schedule["id"], no_wait=args.no_wait)


if __name__ == "__main__":
    raise SystemExit(main())
