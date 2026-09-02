"""Feed ranking pipeline with a branching DAG: score_items fans out into
two independent, parallel stages, which then fan back in at publish_feed.
Every other demo workflow here (feed_success and siblings) is a strict
chain -- one stage in, one stage out -- so none of them ever exercises
the Scheduler's ability to dispatch two ready stages in the same tick, or
to hold a downstream stage back until *all* of its dependencies (not just
one) are done. This one does:

raw_events (injected resource, no stage) -> aggregate_signals -> score_items
    -> rank_feed        --\
    -> trending_topics   ---> publish_feed

rank_feed and trending_topics both depend only on score_items and share
no dependency on each other, so the Scheduler dispatches them together as
soon as score_items completes; publish_feed depends on both and won't
dispatch until they're both done, regardless of which one finishes first.

`raw_events` has to already exist in the Resource Store before this runs
-- see `resource upload` in the CLI.

Importing this package registers every stage into `registry` (each stage
file registers itself as a side effect of being imported below); `registry`
is what the Scheduler actually runs.
"""

from .registry import registry
from . import (  # noqa: F401 -- imported for their registration side effects
    aggregate_signals,
    score_items,
    rank_feed,
    trending_topics,
    publish_feed,
)

__all__ = ["registry"]
