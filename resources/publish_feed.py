"""Declared contract for the `publish_feed` resource: a workflow's
terminal output. Deliberately light -- it's a straight passthrough of
`rank_feed` (already validated on its own way in), and nothing downstream
consumes this value, so there's no business rule to enforce here beyond
"a resource still needs a declared contract to be uploadable at all."
"""

from __future__ import annotations

from typing import Any


def validate(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError(f"publish_feed must be a list, got {type(value).__name__}")
