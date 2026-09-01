"""Loads a workflow project (a directory under workflows/, e.g.
workflows/feed_success/) as a real Python package, so its stage files can
use ordinary relative imports (`from .registry import registry`) to share
one StageRegistry, instead of needing ad-hoc file-loading tricks.

Adds the workflow directory's *parent* to sys.path -- not the workflow
directory itself, and not workflows/ permanently -- so the project's own
name becomes importable for exactly this call, without requiring
workflows/ to be a package or to live inside any service's source tree.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from stages import StageRegistry


def load_workflow(workflow_dir: Path) -> StageRegistry:
    workflow_dir = workflow_dir.resolve()
    parent = str(workflow_dir.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    module = importlib.import_module(workflow_dir.name)

    registry = getattr(module, "registry", None)
    if not isinstance(registry, StageRegistry):
        raise ValueError(
            f"{workflow_dir} has no `registry: StageRegistry` exposed from its __init__.py"
        )
    return registry
