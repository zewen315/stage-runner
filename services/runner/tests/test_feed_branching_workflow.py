"""Regression test for the checked-in feed_branching example workflow --
the one demo workflow with an actual branching DAG (every other one here
is a strict chain). Proves the Scheduler-shaped dispatch loop this test
drives (topological_order, one stage at a time, inputs pinned to specific
upstream output versions) correctly fans a single upstream stage
(score_items) out into two independent downstream stages (rank_feed,
trending_topics), and fans back in at publish_feed, which depends on
both and merges their outputs.

Patches out time.sleep: see test_feed_success_workflow.py for why.
"""

from pathlib import Path
from unittest.mock import patch

from dag import topological_order
from resource_store_client import InMemoryResourceClient
from workflow_loader import load_workflow

from runner import Runner

WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "workflows" / "feed_branching"

RAW_EVENTS = [
    {"item_id": "post_1", "event": "impression"},
    {"item_id": "post_1", "event": "impression"},
    {"item_id": "post_1", "event": "click"},
    {"item_id": "post_1", "event": "like"},
    {"item_id": "post_2", "event": "impression"},
    {"item_id": "post_2", "event": "impression"},
    {"item_id": "post_2", "event": "impression"},
    {"item_id": "post_3", "event": "impression"},
    {"item_id": "post_3", "event": "click"},
    {"item_id": "post_3", "event": "click"},
    {"item_id": "post_3", "event": "like"},
    {"item_id": "post_3", "event": "like"},
]


@patch("time.sleep")
def test_feed_branching_fans_out_and_merges_back_in(mock_sleep, tmp_path):
    registry = load_workflow(WORKFLOW_DIR)
    resources = InMemoryResourceClient()
    runner = Runner(resources, workflow_dir=WORKFLOW_DIR)

    raw_events_version = resources.upload_version("raw_events", RAW_EVENTS)
    resources.promote("raw_events", raw_events_version)
    done: dict[str, int] = {"raw_events": raw_events_version}

    for stage_def in topological_order(registry.all()):
        input_versions = {dep: done[dep] for dep in stage_def.depends_on}
        outcome = runner.run_stage(stage_def, input_versions, promote=True)
        assert outcome.error is None, f"{stage_def.name} failed: {outcome.error}"
        done[stage_def.name] = outcome.version

    _, ranked = resources.get("rank_feed")
    assert [item["item_id"] for item in ranked] == ["post_3", "post_1", "post_2"]

    _, trending = resources.get("trending_topics")
    assert sorted(trending) == ["post_1", "post_3"]  # post_2's score (0) never clears the threshold

    _, published = resources.get("publish_feed")
    assert published == [
        {"item_id": "post_3", "score": 21.0, "trending": True},
        {"item_id": "post_1", "score": 5.5, "trending": True},
        {"item_id": "post_2", "score": 0.0, "trending": False},
    ]

    # publish_feed depends on both rank_feed and trending_topics -- prove
    # the Scheduler-shaped loop above actually dispatched both branches
    # (not just the one publish_feed happens to read most of its shape
    # from), by checking both are recorded as its dependencies.
    dependencies = resources.dependencies_recorded[("publish_feed", done["publish_feed"])]
    assert set(dependencies) == {("rank_feed", done["rank_feed"]), ("trending_topics", done["trending_topics"])}
