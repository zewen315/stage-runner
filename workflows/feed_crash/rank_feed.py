import time

from .registry import registry


@registry.stage("rank_feed", depends_on=["score_items"])
def rank_feed(score_items: dict) -> list[dict]:
    time.sleep(10)
    ranked = sorted(score_items.items(), key=lambda pair: pair[1], reverse=True)
    return [{"item_id": item_id, "score": score} for item_id, score in ranked]
