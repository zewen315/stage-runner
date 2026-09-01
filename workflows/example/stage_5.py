"""Final stage: depends on stage_4. Sleeps 10s, then produces the
pipeline's end result."""

import time

from .registry import registry


@registry.stage("stage_5", depends_on=["stage_4"])
def stage_5(stage_4: dict) -> dict:
    time.sleep(10)
    return {"value": stage_4["value"] + 1}
