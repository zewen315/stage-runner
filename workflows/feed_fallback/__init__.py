"""Feed ranking pipeline, `score_items` variant: raises instead of
returning, after the usual 10s -- same crash as `feed_crash`. The
difference is the registry's `on_failure="fallback"`: instead of halting,
the Scheduler treats `score_items` as if it had produced its
currently-promoted version, and `rank_feed`/`publish_feed` still run
against that (possibly stale) value. The run reaches `completed`; the
`score_items` StageRun itself still records `status="failed"` with the
real error, fully auditable via `GET .../runs/{id}/stage-runs` -- nothing
is hidden, just not surfaced as a top-level run failure. Requires
`score_items` to already have a promoted version from a prior successful
run (e.g. `feed_success`) -- resource identity is global, so any
workflow's success counts. With no such version, this degrades to halting,
same as `feed_crash`.

raw_events (injected resource, no stage) -> aggregate_signals -> score_items (crashes, falls back) -> rank_feed -> publish_feed

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
