from .registry import registry


@registry.stage("score_items", depends_on=["aggregate_signals"])
def score_items(aggregate_signals: dict) -> dict:
    """Simple weighted score -- not a real model, just enough to rank."""
    scores = {}
    for item_id, signals in aggregate_signals.items():
        impressions = max(signals["impressions"], 1)
        ctr = signals["clicks"] / impressions
        scores[item_id] = round(ctr * 10 + signals["likes"] * 0.5, 4)
    return scores
