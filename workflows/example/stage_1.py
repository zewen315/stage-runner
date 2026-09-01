"""Entry stage: no dependencies. Sleeps 10s to simulate work, then passes
a simple value downstream."""

import time

from .registry import registry


@registry.stage("stage_1", depends_on=[])
def stage_1() -> dict:
    time.sleep(10)
    return {"value": 1}
