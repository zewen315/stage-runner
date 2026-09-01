"""Loads a resource's validator from resources/<name>.py -- the resource's
declared contract, the same idea as `lib/workflow_loader.py` loading a
workflow's StageRegistry from workflows/<name>/, just simpler: a resource
is one flat file (`resources/<name>.py`, a plain module -- not a package
like a workflow), not a whole registry of stages to aggregate.

No caching, same as workflow loading elsewhere in this project -- a
resource's validator code changes take effect on the next call, not
immediately on every edit; restarting the service is how that's picked up
today, exactly like workflow code already behaves.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from errors import ResourceValidationError


class FileResourceValidatorLoader:
    def __init__(self, resources_root: Path):
        self._resources_root = resources_root.resolve()

    def load(self, name: str) -> Callable[[Any], None]:
        path = str(self._resources_root)
        if path not in sys.path:
            sys.path.insert(0, path)

        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            raise ResourceValidationError(
                f"resource {name!r} has no declared contract "
                f"({self._resources_root / f'{name}.py'} not found)"
            ) from exc

        validate = getattr(module, "validate", None)
        if not callable(validate):
            raise ResourceValidationError(
                f"{self._resources_root / f'{name}.py'} has no `validate(value)` function"
            )
        return validate

    def list_names(self) -> list[str]:
        """Every declared resource -- the code-side registry of valid
        names, the same role workflows/*/ plays for WorkflowService.list_workflows()."""
        if not self._resources_root.is_dir():
            return []
        return sorted(
            path.stem
            for path in self._resources_root.glob("*.py")
            if not path.stem.startswith(("_", "."))
        )
