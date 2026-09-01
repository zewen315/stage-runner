import time

from .registry import registry

_EVENT_TO_FIELD = {"impression": "impressions", "click": "clicks", "like": "likes"}


@registry.stage("aggregate_signals", depends_on=["raw_events"])
def aggregate_signals(raw_events: list[dict]) -> dict:
    """raw_events: [{"item_id": str, "event": "impression"|"click"|"like"}, ...]"""
    time.sleep(10)
    signals: dict[str, dict[str, int]] = {}
    for event in raw_events:
        item = signals.setdefault(
            event["item_id"], {"impressions": 0, "clicks": 0, "likes": 0}
        )
        item[_EVENT_TO_FIELD[event["event"]]] += 1
    return signals
