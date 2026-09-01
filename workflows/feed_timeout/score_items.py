import time

from .registry import registry


@registry.stage("score_items", depends_on=["aggregate_signals"])
def score_items(aggregate_signals: dict) -> dict:
    """Simulates a stage that runs far longer than expected -- sleeps 60s
    against the rest of the workflow's 10s baseline. Stage Runner doesn't
    enforce execution timeouts yet; this is the stage that would trip one
    once that exists. For now, running this workflow just takes longer."""
    time.sleep(60)
    scores = {}
    for item_id, signals in aggregate_signals.items():
        impressions = max(signals["impressions"], 1)
        ctr = signals["clicks"] / impressions
        scores[item_id] = round(ctr * 10 + signals["likes"] * 0.5, 4)
    return scores
