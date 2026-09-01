"""Declared contract for the `aggregate_signals` resource: a dict of
item_id -> per-item counts, each count a non-negative integer.
"""

from __future__ import annotations

from typing import Any

_REQUIRED_FIELDS = {"impressions", "clicks", "likes"}


def validate(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"aggregate_signals must be an object, got {type(value).__name__}")

    for item_id, signals in value.items():
        if not isinstance(signals, dict) or set(signals) != _REQUIRED_FIELDS:
            raise ValueError(
                f"aggregate_signals[{item_id!r}] must have exactly {sorted(_REQUIRED_FIELDS)}, "
                f"got {signals!r}"
            )
        for field, count in signals.items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(
                    f"aggregate_signals[{item_id!r}].{field} must be a non-negative integer, got {count!r}"
                )
