"""Usage: uv run python cli/stagerunner.py run <workflow-name> [--base-url URL] [--no-wait]

Thin client: this only ever talks HTTP to the Workflow Service (through the
gateway, by default). It requests a run and optionally polls for its
outcome -- it has no DAG/execution logic of its own, no knowledge of the
Resource Store, and no dependency on the Scheduler's internals. Actually
running a workflow happens elsewhere, asynchronously, via the Scheduler
worker consuming the queue the Workflow Service publishes to.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stagerunner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Request a workflow run")
    run_parser.add_argument("workflow", help="workflow name, e.g. feed_ranking")
    run_parser.add_argument(
        "--base-url", default="http://localhost:8080", help="API gateway base URL"
    )
    run_parser.add_argument(
        "--no-wait", action="store_true", help="Request the run and return immediately"
    )

    args = parser.parse_args(argv)

    client = httpx.Client(base_url=args.base_url)
    response = client.post(f"/workflows/{args.workflow}/runs")
    if response.status_code == 404:
        print(f"error: no workflow {args.workflow!r}", file=sys.stderr)
        return 1
    response.raise_for_status()
    run = response.json()
    print(f"requested run {run['id']} for {args.workflow!r} (status={run['status']})")

    if args.no_wait:
        return 0

    while run["status"] in ("requested", "running"):
        time.sleep(0.5)
        response = client.get(f"/workflows/{args.workflow}/runs/{run['id']}")
        response.raise_for_status()
        run = response.json()

    print(f"run {run['id']}: {run['status']}")
    if run["status"] == "failed":
        print(f"error: {run['error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
