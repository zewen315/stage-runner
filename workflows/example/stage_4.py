"""Depends on stage_3. Sleeps 10s, then passes its value along, incremented
by one."""

import time

from .registry import registry


@registry.stage("stage_4", depends_on=["stage_3"])
def stage_4(stage_3: dict) -> dict:
    time.sleep(10)
    return {"value": stage_3["value"] + 1}
