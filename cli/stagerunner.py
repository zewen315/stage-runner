"""Usage:
  uv run python cli/stagerunner.py run <workflow-name>
      [--stage NAME | --start-from NAME] [--stop-after NAME]
      [--input <resource>=<version> ...] [--promote] [--at TIMESTAMP]
      [--base-url URL] [--no-wait]

  uv run python cli/stagerunner.py resource upload <name> <file>
      [--promote | --no-promote] [--base-url URL]

Thin client: this only ever talks HTTP -- to the Workflow Service for
`run`, to the Resource Store for `resource upload` (both through the
gateway, by default). It has no DAG/execution logic of its own and no
dependency on the Scheduler's or Runner's internals.

`run` only ever creates a `schedules` row; actually dispatching and
running it happens elsewhere, asynchronously: the Scheduler drains
`schedules` and dispatches stage-by-stage, and the Runner worker executes
exactly one stage per dispatch.

Every run is a WorkflowRun -- `--stage`/`--start-from`/`--stop-after`
narrow it to a sub-range of the workflow's DAG rather than naming a
different kind of thing. Plain `run <workflow>` runs the whole DAG.
`--stage NAME` is sugar for `--start-from NAME --stop-after NAME` (run
just that one stage). `--start-from NAME` alone resumes the rest of the
pipeline from that stage onward. `--stop-after NAME` alone runs from the
natural roots and stops once that stage completes.

`--at TIMESTAMP` (ISO 8601; assumed UTC if it has no timezone) delays
dispatch until then instead of as soon as the Scheduler sees it -- the
schedule sits undispatched (visible via `GET .../schedules/{id}`) until
its time arrives. Implies `--no-wait`: polling for a run that won't start
for an hour isn't useful.

`resource upload` is how a workflow root (a stage-less dependency, e.g.
`raw_events`) gets its value into the system in the first place -- every
stage's input and output is a resource, so there's no other way in. Reads
`file` as JSON and uploads it as a new version; promotes by default (unlike
`run`'s `--promote`) since an injected root is useless to a run until it's
current.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def _parse_input(raw: str) -> tuple[str, int]:
    name, _, version = raw.partition("=")
    if not version:
        raise argparse.ArgumentTypeError(f"expected <resource>=<version>, got {raw!r}")
    return name, int(version)


def _parse_at(raw: str) -> str:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an ISO 8601 timestamp, got {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


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


def _run(args: argparse.Namespace) -> int:
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
    if args.at is not None:
        body["run_at"] = args.at

    client = httpx.Client(base_url=args.base_url)
    response = client.post(f"/workflows/{args.workflow}/runs", json=body)

    if response.status_code == 404:
        print(f"error: no workflow {args.workflow!r}", file=sys.stderr)
        return 1
    response.raise_for_status()
    schedule = response.json()

    no_wait = args.no_wait or args.at is not None
    return _poll_schedule(client, args.workflow, schedule["id"], no_wait=no_wait)


def _resource_upload(args: argparse.Namespace) -> int:
    value = json.loads(Path(args.file).read_text())

    client = httpx.Client(base_url=args.base_url)
    response = client.post(
        f"/resources/{args.name}/versions", json={"value": value, "is_test": not args.promote}
    )
    if response.status_code == 400:
        print(f"error: {response.json().get('detail', response.text)}", file=sys.stderr)
        return 1
    response.raise_for_status()
    version = response.json()["version"]

    if args.promote:
        client.post(f"/resources/{args.name}/promotions", json={"version": version}).raise_for_status()

    status = "current" if args.promote else "uploaded, not promoted"
    print(f"{args.name} v{version}: {status}")
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
    run_parser.add_argument(
        "--at",
        metavar="TIMESTAMP",
        type=_parse_at,
        help="delay dispatch until this time (ISO 8601, assumed UTC if no timezone given); implies --no-wait",
    )
    run_parser.add_argument("--base-url", default="http://localhost:8080", help="API gateway base URL")
    run_parser.add_argument(
        "--no-wait", action="store_true", help="Request the run and return immediately"
    )

    resource_parser = subparsers.add_parser("resource", help="Manage resources directly")
    resource_subparsers = resource_parser.add_subparsers(dest="resource_command", required=True)

    upload_parser = resource_subparsers.add_parser(
        "upload", help="Upload a JSON file as a new resource version"
    )
    upload_parser.add_argument("name", help="resource name, e.g. raw_events")
    upload_parser.add_argument("file", help="path to a JSON file holding the resource's value")
    upload_parser.add_argument(
        "--promote",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="make this version current (default: true -- an unpromoted upload isn't visible to a run "
        "unless pinned by --input)",
    )
    upload_parser.add_argument("--base-url", default="http://localhost:8080", help="API gateway base URL")

    args = parser.parse_args(argv)

    if args.command == "run":
        if args.stage is not None and (args.start_from is not None or args.stop_after is not None):
            run_parser.error("--stage cannot be combined with --start-from/--stop-after")
        return _run(args)
    return _resource_upload(args)


if __name__ == "__main__":
    raise SystemExit(main())
