"""Feed ranking pipeline, happy path: ingest events -> aggregate signals ->
score -> rank -> publish. Every real compute stage sleeps 10s (import/export
are plain file I/O, no delay) so the Scheduler's stage-by-stage dispatch is
visible live -- see `docker compose logs -f scheduler runner`.

raw_events (import) -> aggregate_signals -> score_items -> rank_feed -> publish_feed (export)

Siblings `feed_timeout`, `feed_crash`, and `feed_validation_failed` are
identical except `score_items` misbehaves in one specific way each --
useful for exercising failure/rollback paths without touching this one.

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
