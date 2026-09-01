"""Example pipeline: five simple stages, mostly just `sleep(10)`, wired
together so dependency dispatch is visible without any real domain logic.

stage_1 --\
            >-- stage_3 -> stage_4 -> stage_5
stage_2 --/

Each stage passes a small `{"value": int}` resource downstream so there's
something concrete to watch flow through the DAG. stage_1 and stage_2 have
no dependencies and are both ready immediately; stage_3 only becomes ready
once *both* have completed; stage_4 and stage_5 follow one at a time after
that. Watch it live with `docker compose logs -f scheduler runner`.

Importing this package registers every stage into `registry` (each stage
file registers itself as a side effect of being imported below); `registry`
is what the Scheduler actually runs against.
"""

from .registry import registry
from . import (  # noqa: F401 -- imported for their registration side effects
    stage_1,
    stage_2,
    stage_3,
    stage_4,
    stage_5,
)

__all__ = ["registry"]
