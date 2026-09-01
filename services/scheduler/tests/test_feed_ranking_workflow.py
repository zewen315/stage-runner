"""Regression test for the checked-in example workflow itself -- proves the
real feed_ranking pipeline computes the expected ranking end to end, not
just that the scheduler machinery works in the abstract.
"""

from pathlib import Path

from resource_store_client import InMemoryResourceClient

from runner import Runner
from scheduler import Scheduler
from workflow_loader import load_workflow

WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "workflows" / "feed_ranking"


def test_feed_ranking_produces_expected_order(tmp_path):
    registry = load_workflow(WORKFLOW_DIR)
    resources = InMemoryResourceClient()
    # output_dir is a tmp dir, not WORKFLOW_DIR -- the workflow directory is
    # checked-in content and shouldn't be written to by a run (matches the
    # read-only mount used in docker-compose).
    runner = Runner(resources, workflow_dir=WORKFLOW_DIR, output_dir=tmp_path)

    result = Scheduler(registry, runner).run()

    assert result.failed is None
    _, feed = resources.get("rank_feed")
    assert [item["item_id"] for item in feed] == ["post_3", "post_1", "post_2"]
    assert (tmp_path / "feed.json").exists()
