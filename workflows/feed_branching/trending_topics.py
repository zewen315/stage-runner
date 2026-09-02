import time

from .registry import registry

_TRENDING_THRESHOLD = 5.0


@registry.stage("trending_topics", depends_on=["score_items"])
def trending_topics(score_items: dict) -> list[str]:
    """Runs in parallel with rank_feed -- both branch directly off
    score_items, and publish_feed doesn't dispatch until both of them
    have. A different, independent read of the same score_items output:
    which items cleared a flat threshold, regardless of rank."""
    time.sleep(10)
    return [item_id for item_id, score in score_items.items() if score >= _TRENDING_THRESHOLD]
