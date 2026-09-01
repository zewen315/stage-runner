"""Container-side entrypoint: runs exactly one stage's pure function in
isolation, given its already-resolved input values -- not versions. The
calling Runner process, outside this container, already did all the
resource_store I/O; this process never touches resource_store or the
network at all, only WORKFLOW_NAME/STAGE_NAME/STAGE_INPUTS_JSON and the
same read-only workflows/ mount every other service uses.

Writes exactly one line of JSON to stdout -- {"ok": true, "result": ...}
on success, {"ok": false, "error": ...} on failure -- and exits 0/1
accordingly. This is what DockerStageExecutor (stage_executor.py) expects
back.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from workflow_loader import load_workflow


def main() -> int:
    workflow_name = os.environ["WORKFLOW_NAME"]
    stage_name = os.environ["STAGE_NAME"]
    inputs = json.loads(os.environ.get("STAGE_INPUTS_JSON", "{}"))
    workflows_root = Path(os.environ.get("WORKFLOWS_ROOT", "/workflows"))

    try:
        registry = load_workflow(workflows_root / workflow_name)
        stage_def = registry.get(stage_name)
        result = stage_def.fn(**inputs)
    except Exception as exc:  # noqa: BLE001 -- report and exit, don't traceback-dump
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps({"ok": True, "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
