import time

from .registry import registry


@registry.stage("score_items", depends_on=["aggregate_signals"])
def score_items(aggregate_signals: dict) -> dict:
    """Simulates a stage that silently produces the wrong shape: scores
    come out as strings instead of numbers. Nothing catches this today --
    resource_store has no schema validation yet (see AI_WORKFLOW.md /
    SYSTEM_DESIGN.md), so the run "succeeds" and rank_feed downstream just
    sorts lexicographically instead of numerically, a quiet correctness
    bug rather than a crash. This workflow exists to demonstrate exactly
    that gap -- it should start failing loudly the moment resource schema
    validation lands."""
    time.sleep(10)
    scores = {}
    for item_id, signals in aggregate_signals.items():
        impressions = max(signals["impressions"], 1)
        ctr = signals["clicks"] / impressions
        scores[item_id] = str(round(ctr * 10 + signals["likes"] * 0.5, 4))
    return scores
