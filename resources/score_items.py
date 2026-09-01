"""Declared contract for the `score_items` resource: a dict of
item_id -> numeric score.
"""

from __future__ import annotations

from typing import Any


def validate(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"score_items must be an object, got {type(value).__name__}")

    for item_id, score in value.items():
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"score_items[{item_id!r}] must be numeric, got {type(score).__name__}")
