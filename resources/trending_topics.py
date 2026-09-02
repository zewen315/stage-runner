"""Declared contract for the `trending_topics` resource: a list of
item_ids (a subset of `score_items`' keys) that crossed the trending
threshold, no duplicates.
"""

from __future__ import annotations

from typing import Any


def validate(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError(f"trending_topics must be a list, got {type(value).__name__}")

    seen_ids: set[str] = set()
    for i, item_id in enumerate(value):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"trending_topics[{i}] must be a non-empty string, got {item_id!r}")
        if item_id in seen_ids:
            raise ValueError(f"trending_topics contains duplicate item_id {item_id!r}")
        seen_ids.add(item_id)
