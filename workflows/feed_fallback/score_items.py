import time

from .registry import registry


@registry.stage("score_items", depends_on=["aggregate_signals"])
def score_items(aggregate_signals: dict) -> dict:
    """Simulates a stage that crashes outright -- runs for the normal 10s,
    then raises instead of returning. Exercises the failure path worker
    -> Scheduler -> WorkflowRun marked failed, no rollback machinery
    needed to make sense of it: the resource simply never gets a new
    version."""
    time.sleep(10)
    raise RuntimeError("simulated crash in score_items")
