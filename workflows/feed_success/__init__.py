"""Feed ranking pipeline, happy path: ingest events -> aggregate signals ->
score -> rank -> publish. Every stage sleeps 10s so the Scheduler's
stage-by-stage dispatch is visible live -- see
`docker compose logs -f scheduler runner`.

raw_events (injected resource, no stage) -> aggregate_signals -> score_items -> rank_feed -> publish_feed

`raw_events` has to already exist in the Resource Store before this runs
-- see `resource upload` in the CLI.

Siblings `feed_timeout`, `feed_crash`, and `feed_validation_failed` are
identical except `score_items` misbehaves in one specific way each --
useful for exercising failure/rollback paths without touching this one.

Importing this package registers every stage into `registry` (each stage
file registers itself as a side effect of being imported below); `registry`
is what the Scheduler actually runs.
"""

from .registry import registry
from . import (  # noqa: F401 -- imported for their registration side effects
    aggregate_signals,
    score_items,
    rank_feed,
    publish_feed,
)

__all__ = ["registry"]
