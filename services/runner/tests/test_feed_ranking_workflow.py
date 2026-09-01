"""Regression test for the checked-in example workflow itself -- proves the
real feed_ranking pipeline computes the expected ranking end to end,
driven exactly the way the Scheduler drives it in production: one stage at
a time, in dependency order, each stage's inputs pinned to the specific
upstream output versions produced so far in *this* run (never "current").
"""

from pathlib import Path

from dag import topological_order
from resource_store_client import InMemoryResourceClient
from workflow_loader import load_workflow

from runner import Runner

WORKFLOW_DIR = Path(__file__).resolve().parents[3] / "workflows" / "feed_ranking"


def test_feed_ranking_produces_expected_order(tmp_path):
    registry = load_workflow(WORKFLOW_DIR)
    resources = InMemoryResourceClient()
    # output_dir is a tmp dir, not WORKFLOW_DIR -- the workflow directory is
    # checked-in content and shouldn't be written to by a run (matches the
    # read-only mount used in docker-compose).
    runner = Runner(resources, workflow_dir=WORKFLOW_DIR, output_dir=tmp_path)

    done: dict[str, int] = {}
    for stage_def in topological_order(registry.all()):
        input_versions = {dep: done[dep] for dep in stage_def.depends_on}
        output_version = runner.run_stage(stage_def, input_versions, promote=True)
        if output_version is not None:
            done[stage_def.name] = output_version

    _, feed = resources.get("rank_feed")
    assert [item["item_id"] for item in feed] == ["post_3", "post_1", "post_2"]
    assert (tmp_path / "feed.json").exists()
