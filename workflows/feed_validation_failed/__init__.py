"""Feed ranking pipeline, `score_items` variant: scores come out as
strings instead of numbers -- a schema violation nothing catches today,
since resource_store has no validation yet (deliberately dropped, see
AI_WORKFLOW.md / SYSTEM_DESIGN.md). The run "succeeds"; `rank_feed`
downstream just sorts lexicographically instead of numerically -- a quiet
correctness bug, not a crash. Exists to demonstrate that gap: this
workflow should start failing loudly the moment resource schema
validation lands. Otherwise identical to `feed_success`.

raw_events (import) -> aggregate_signals -> score_items (wrong shape) -> rank_feed -> publish_feed (export)

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
