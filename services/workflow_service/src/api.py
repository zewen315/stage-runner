"""FastAPI app exposing WorkflowService over HTTP.

Two callers, two halves of the API:
- client-facing: POST a run request, GET its status. This is the entire
  surface the CLI (or a future UI) talks to.
- worker-facing: start/complete/fail. Only the Scheduler worker calls
  these, as it consumes the queue and makes progress on a run.

Backed by real Postgres + Redis when DATABASE_URL/REDIS_URL are set
(docker-compose sets them), in-memory otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from errors import RunNotFoundError, WorkflowNotFoundError
from memory import InMemoryRunQueue, InMemoryRunRepository
from service import WorkflowService


def _build_service() -> WorkflowService:
    workflows_root = Path(os.environ.get("WORKFLOWS_ROOT", "../../workflows")).resolve()
    database_url = os.environ.get("DATABASE_URL")
    redis_url = os.environ.get("REDIS_URL")

    if database_url is None or redis_url is None:
        return WorkflowService(InMemoryRunRepository(), InMemoryRunQueue(), workflows_root)

    from postgres_repository import PostgresRunRepository
    from redis_queue import RedisRunQueue

    return WorkflowService(PostgresRunRepository(database_url), RedisRunQueue(redis_url), workflows_root)


app = FastAPI(title="Workflow Service")

_service = _build_service()


def get_service() -> WorkflowService:
    return _service


@app.exception_handler(WorkflowNotFoundError)
async def handle_workflow_not_found(request: Request, exc: WorkflowNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(RunNotFoundError)
async def handle_run_not_found(request: Request, exc: RunNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_name: str
    status: str
    requested_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None


class FailRunRequest(BaseModel):
    error: str


@app.post("/workflows/{name}/runs", response_model=RunResponse, status_code=202)
def request_run(name: str, service: WorkflowService = Depends(get_service)):
    return service.request_run(name)


@app.get("/workflows/{name}/runs/{run_id}", response_model=RunResponse)
def get_run(name: str, run_id: int, service: WorkflowService = Depends(get_service)):
    return service.get_run(name, run_id)


@app.post("/workflows/{name}/runs/{run_id}/start", status_code=204)
def start_run(name: str, run_id: int, service: WorkflowService = Depends(get_service)) -> None:
    service.start_run(name, run_id)


@app.post("/workflows/{name}/runs/{run_id}/complete", status_code=204)
def complete_run(name: str, run_id: int, service: WorkflowService = Depends(get_service)) -> None:
    service.complete_run(name, run_id)


@app.post("/workflows/{name}/runs/{run_id}/fail", status_code=204)
def fail_run(
    name: str, run_id: int, body: FailRunRequest, service: WorkflowService = Depends(get_service)
) -> None:
    service.fail_run(name, run_id, body.error)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
