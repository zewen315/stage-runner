"""Regression test for the checked-in example workflow itself -- proves the
real feed_ranking pipeline computes the expected ranking end to end, not
just that the scheduler machinery works in the abstract.
"""

import shutil
from pathlib import Path

from resource_store_client import InMemoryResourceClient

from runner import Runner
from scheduler import Scheduler
from workflow_loader import load_workflow

WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "workflows" / "feed_ranking"


def test_feed_ranking_produces_expected_order():
    registry = load_workflow(WORKFLOW_DIR)
    resources = InMemoryResourceClient()
    runner = Runner(resources, workflow_dir=WORKFLOW_DIR)

    try:
        result = Scheduler(registry, runner).run()

        assert result.failed is None
        _, feed = resources.get("rank_feed")
        assert [item["item_id"] for item in feed] == ["post_3", "post_1", "post_2"]
    finally:
        shutil.rmtree(WORKFLOW_DIR / "output", ignore_errors=True)
