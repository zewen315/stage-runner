"""Declared contract for the `rank_feed` resource: a list of
{"item_id", "score"}, no duplicate ids, sorted by score descending -- a
business-rule check, not just a structural one.
"""

from __future__ import annotations

from typing import Any


def validate(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError(f"rank_feed must be a list, got {type(value).__name__}")

    seen_ids: set[str] = set()
    previous_score: float | None = None

    for i, entry in enumerate(value):
        if not isinstance(entry, dict) or set(entry) != {"item_id", "score"}:
            raise ValueError(f"rank_feed[{i}] must have exactly item_id and score, got {entry!r}")

        item_id, score = entry["item_id"], entry["score"]

        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"rank_feed[{i}].item_id must be a non-empty string, got {item_id!r}")
        if item_id in seen_ids:
            raise ValueError(f"rank_feed contains duplicate item_id {item_id!r}")
        seen_ids.add(item_id)

        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"rank_feed[{i}].score must be numeric, got {type(score).__name__}")
        if previous_score is not None and score > previous_score:
            raise ValueError("rank_feed must be sorted by score, descending")
        previous_score = score
