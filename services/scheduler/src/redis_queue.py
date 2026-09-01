"""Redis-backed RunQueue: a plain list used as a FIFO work queue
(LPUSH/BRPOP). QUEUE_KEY is shared with the Runner worker, which is the
only consumer. Only StageRuns are ever queued -- a WorkflowRun is never
dispatched, it's a pure tracking record the Scheduler's progression pass
keeps revisiting.
"""

from __future__ import annotations

import json

import redis

QUEUE_KEY = "stagerunner:stage_runs"


class RedisRunQueue:
    def __init__(self, redis_url: str):
        self._client = redis.from_url(redis_url)

    def enqueue_stage_run(
        self,
        stage_run_id: int,
        workflow_run_id: int,
        workflow_name: str,
        stage_name: str,
        input_versions: dict[str, int],
        promote: bool,
    ) -> None:
        message = {
            "stage_run_id": stage_run_id,
            "workflow_run_id": workflow_run_id,
            "workflow_name": workflow_name,
            "stage_name": stage_name,
            "input_versions": input_versions,
            "promote": promote,
        }
        self._client.lpush(QUEUE_KEY, json.dumps(message))
