"""Terminal stage: every workflow ends by producing a resource, this one
included -- there's no separate "export the result somewhere" step.
Nothing downstream depends on it, and nothing about its value is
meaningful beyond being what the run produced; it passes rank_feed
through unchanged."""

from .registry import registry


@registry.stage("publish_feed", depends_on=["rank_feed"])
def publish_feed(rank_feed: list[dict]) -> list[dict]:
    return rank_feed
