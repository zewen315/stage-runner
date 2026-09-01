"""Entry stage: no dependencies, the pipeline's other entry point alongside
stage_1. Sleeps 10s, then passes a simple value downstream."""

import time

from .registry import registry


@registry.stage("stage_2", depends_on=[])
def stage_2() -> dict:
    time.sleep(10)
    return {"value": 2}
