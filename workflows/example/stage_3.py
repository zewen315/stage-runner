"""Depends on both entry stages. Sleeps 10s, then combines their values --
the first point in the pipeline where two upstream resources actually
meet."""

import time

from .registry import registry


@registry.stage("stage_3", depends_on=["stage_1", "stage_2"])
def stage_3(stage_1: dict, stage_2: dict) -> dict:
    time.sleep(10)
    return {"value": stage_1["value"] + stage_2["value"]}
