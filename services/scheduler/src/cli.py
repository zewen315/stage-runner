"""Usage: uv run python src/cli.py run <path/to/workflow_dir> [--base-url URL]

Run directly as a script (not `-m`) so the script's own directory (src/) is
on sys.path automatically -- that's what makes `stages`/`workflow_loader`
resolve without extra path config.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# lib/ holds modules shared across services (e.g. resource_store_client);
# pytest gets this via pythonpath in pyproject.toml, but a plain script
# invocation needs it added explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from resource_store_client import HttpResourceClient  # noqa: E402
from runner import Runner  # noqa: E402
from scheduler import Scheduler  # noqa: E402
from workflow_loader import load_workflow  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stagerunner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a workflow project's stages in dependency order")
    run_parser.add_argument("workflow", help="path to a workflow directory, e.g. workflows/feed_ranking")
    run_parser.add_argument("--base-url", default="http://localhost:8000", help="Resource Store base URL")

    args = parser.parse_args(argv)

    workflow_dir = Path(args.workflow).resolve()
    try:
        registry = load_workflow(workflow_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    resources = HttpResourceClient(args.base_url)
    runner = Runner(resources, workflow_dir=workflow_dir)
    result = Scheduler(registry, runner).run()

    for name in result.completed:
        print(f"  ok    {name}")

    if result.failed:
        print(f"  FAIL  {result.failed}: {result.error}", file=sys.stderr)
        return 1

    print(f"run complete: {len(result.completed)} stage(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
