"""Regression test for the checked-in example workflow itself -- proves the
real feed_success pipeline computes the expected ranking end to end,
driven exactly the way the Scheduler drives it in production: one stage at
a time, in dependency order, each stage's inputs pinned to the specific
upstream output versions produced so far in *this* run (never "current").
`raw_events` -- the workflow's root -- has no stage; it's seeded here the
same way `resource upload` (the CLI) injects it in practice, standing in
for the Scheduler's own current-version resolution of it (poller.py).

Patches out time.sleep: the workflow's stages sleep 10s each in production
(so the Scheduler's dispatch is visible live), which would make this test
take 30s+ for no benefit here -- it's checking correctness, not timing.
"""

from pathlib import Path
from unittest.mock import patch

from dag import topological_order
from resource_store_client import InMemoryResourceClient
from workflow_loader import load_workflow

from runner import Runner

WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "workflows" / "feed_success"

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
def test_feed_success_produces_expected_order(mock_sleep, tmp_path):
    registry = load_workflow(WORKFLOW_DIR)
    resources = InMemoryResourceClient()
    runner = Runner(resources, workflow_dir=WORKFLOW_DIR)

    raw_events_version = resources.upload_version("raw_events", RAW_EVENTS)
    resources.promote("raw_events", raw_events_version)
    done: dict[str, int] = {"raw_events": raw_events_version}

    for stage_def in topological_order(registry.all()):
        input_versions = {dep: done[dep] for dep in stage_def.depends_on}
        done[stage_def.name] = runner.run_stage(stage_def, input_versions, promote=True)

    _, feed = resources.get("rank_feed")
    assert [item["item_id"] for item in feed] == ["post_3", "post_1", "post_2"]
    _, published = resources.get("publish_feed")
    assert published == feed
