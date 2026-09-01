"""Feed ranking pipeline, `score_items` variant: sleeps 60s instead of the
usual 10s, simulating a stage that runs far longer than expected. Stage
Runner has no execution-timeout enforcement yet, so this just makes the
run slow rather than failing it -- exists to demonstrate that gap.
Otherwise identical to `feed_success`.

raw_events (import) -> aggregate_signals -> score_items (slow) -> rank_feed -> publish_feed (export)

Importing this package registers every stage into `registry` (each stage
file registers itself as a side effect of being imported below); `registry`
is what the Scheduler actually runs.
"""

from .registry import registry
from . import (  # noqa: F401 -- imported for their registration side effects
    raw_events,
    aggregate_signals,
    score_items,
    rank_feed,
    publish_feed,
)

__all__ = ["registry"]
