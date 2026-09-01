"""Feed ranking pipeline, `score_items` variant: raises instead of
returning, after the usual 10s. Exercises the plain failure path -- worker
reports "fail", the Scheduler marks the WorkflowRun failed, downstream
stages never dispatch, and `score_items`/`rank_feed`/`publish_feed` never
get a new resource version. Otherwise identical to `feed_success`.

raw_events (injected resource, no stage) -> aggregate_signals -> score_items (crashes) -x

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
