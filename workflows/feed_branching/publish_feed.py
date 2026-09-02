"""Terminal stage, and the fan-in point of this workflow's branching DAG:
depends on both rank_feed and trending_topics, so the Scheduler won't
dispatch it until *both* parallel branches off score_items have
completed. Merges them -- each ranked item gets a "trending" flag from
the sibling branch's independent read of score_items."""

from .registry import registry


@registry.stage("publish_feed", depends_on=["rank_feed", "trending_topics"])
def publish_feed(rank_feed: list[dict], trending_topics: list[str]) -> list[dict]:
    trending = set(trending_topics)
    return [{**entry, "trending": entry["item_id"] in trending} for entry in rank_feed]
