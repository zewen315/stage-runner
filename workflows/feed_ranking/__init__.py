"""Feed ranking pipeline: ingest events -> aggregate signals -> score ->
rank -> publish.

raw_events (import) -> aggregate_signals -> score_items -> rank_feed -> publish_feed (export)

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
