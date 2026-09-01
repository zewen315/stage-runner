"""Redis-backed RunQueue: a plain list used as a FIFO work queue
(LPUSH/BRPOP). QUEUE_KEY is shared with the Scheduler worker, which is the
only consumer.
"""

from __future__ import annotations

import json

import redis

QUEUE_KEY = "stagerunner:runs"


class RedisRunQueue:
    def __init__(self, redis_url: str):
        self._client = redis.from_url(redis_url)

    def enqueue(self, run_id: int, workflow_name: str) -> None:
        self._client.lpush(QUEUE_KEY, json.dumps({"run_id": run_id, "workflow_name": workflow_name}))
