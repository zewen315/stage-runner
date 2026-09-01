"""Declared contract for the `raw_events` resource: a list of engagement
events, each `{"item_id": str, "event": "impression"|"click"|"like"}`.
"""

from __future__ import annotations

from typing import Any

_VALID_EVENTS = {"impression", "click", "like"}


def validate(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError(f"raw_events must be a list, got {type(value).__name__}")

    for i, event in enumerate(value):
        if not isinstance(event, dict):
            raise ValueError(f"raw_events[{i}] must be an object, got {type(event).__name__}")

        item_id = event.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"raw_events[{i}].item_id must be a non-empty string, got {item_id!r}")

        kind = event.get("event")
        if kind not in _VALID_EVENTS:
            raise ValueError(f"raw_events[{i}].event must be one of {sorted(_VALID_EVENTS)}, got {kind!r}")
