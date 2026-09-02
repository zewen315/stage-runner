"""FastAPI app exposing WorkflowService over HTTP.

Three groups of routes:
- client-facing intake: POST a workflow-level or stage-level trigger
  request, GET its status. This is the entire surface the CLI (or a future
  UI) talks to for triggering work.
- client-facing inspection: GET a WorkflowRun and its StageRuns, or a
  single StageRun directly, for debugging/auditing.
- worker-facing: start/complete/fail on a StageRun. Only the Runner worker
  calls these, as it makes progress on the one stage it was dispatched.

Everything here writes to Postgres and stops -- it never touches Redis and
never creates a `runs`/`stage_runs` row itself. The Scheduler service polls
`schedules` separately, is the sole creator of `runs`/`stage_runs`, and is
the only thing that pushes onto the queue.

Backed by real Postgres when DATABASE_URL is set (docker-compose sets it),
in-memory otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from errors import (
    InvalidCronExpressionError,
    InvalidOnFailureError,
    RecurringScheduleNotFoundError,
    RunNotCancellableError,
    RunNotFoundError,
    ScheduleNotFoundError,
    StageRunNotFoundError,
    WorkflowNotFoundError,
)
from memory import (
    InMemoryRecurringScheduleRepository,
    InMemoryScheduleRepository,
    InMemoryStageRunRepository,
    InMemoryWorkflowRunRepository,
)
from service import WorkflowService


def _build_service() -> WorkflowService:
    workflows_root = Path(os.environ.get("WORKFLOWS_ROOT", "../../workflows")).resolve()
    database_url = os.environ.get("DATABASE_URL")

    if database_url is None:
        return WorkflowService(
            InMemoryScheduleRepository(),
            InMemoryWorkflowRunRepository(),
            InMemoryStageRunRepository(),
            workflows_root,
            InMemoryRecurringScheduleRepository(),
        )

    from postgres_repository import (
        PostgresRecurringScheduleRepository,
        PostgresScheduleRepository,
        PostgresStageRunRepository,
        PostgresWorkflowRunRepository,
    )

    return WorkflowService(
        PostgresScheduleRepository(database_url),
        PostgresWorkflowRunRepository(database_url),
        PostgresStageRunRepository(database_url),
        workflows_root,
        PostgresRecurringScheduleRepository(database_url),
    )


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


@app.exception_handler(StageRunNotFoundError)
async def handle_stage_run_not_found(request: Request, exc: StageRunNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ScheduleNotFoundError)
async def handle_schedule_not_found(request: Request, exc: ScheduleNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(RecurringScheduleNotFoundError)
async def handle_recurring_schedule_not_found(
    request: Request, exc: RecurringScheduleNotFoundError
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidCronExpressionError)
async def handle_invalid_cron_expression(request: Request, exc: InvalidCronExpressionError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RunNotCancellableError)
async def handle_run_not_cancellable(request: Request, exc: RunNotCancellableError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(InvalidOnFailureError)
async def handle_invalid_on_failure(request: Request, exc: InvalidOnFailureError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    run_at: str | None
    status: str
    error: str | None
    run_id: int | None


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_name: str
    start_from: str | None
    stop_after: str | None
    promote: bool
    status: str
    requested_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    cancel_requested: bool
    on_failure: str | None


class StageRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_run_id: int
    workflow_name: str
    stage_name: str
    input_versions: dict[str, int]
    promote: bool
    output_version: int | None
    status: str
    requested_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    attempts: int
    used_fallback: bool


class StageInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    depends_on: list[str]
    retries: int


class RecurringScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_name: str
    cron_expression: str
    start_from: str | None
    stop_after: str | None
    input_versions: dict[str, int] | None
    promote: bool | None
    enabled: bool
    next_run_at: str
    created_at: str
    on_failure: str | None


class RequestRunRequest(BaseModel):
    start_from: str | None = None
    stop_after: str | None = None
    input_versions: dict[str, int] | None = None
    promote: bool | None = None
    run_at: str | None = None
    on_failure: str | None = None


class CreateRecurringScheduleRequest(BaseModel):
    cron_expression: str
    start_from: str | None = None
    stop_after: str | None = None
    input_versions: dict[str, int] | None = None
    promote: bool | None = None
    on_failure: str | None = None


class CompleteStageRunRequest(BaseModel):
    output_version: int | None = None
    attempts: int = 1


class FailStageRunRequest(BaseModel):
    error: str
    attempts: int = 1


@app.get("/workflows", response_model=list[str])
def list_workflows(service: WorkflowService = Depends(get_service)):
    return service.list_workflows()


@app.get("/workflows/{name}/stages", response_model=list[StageInfoResponse])
def list_stages(name: str, service: WorkflowService = Depends(get_service)):
    return service.list_stages(name)


@app.post("/workflows/{name}/runs", response_model=ScheduleResponse, status_code=202)
def request_run(
    name: str,
    body: RequestRunRequest | None = None,
    service: WorkflowService = Depends(get_service),
):
    body = body or RequestRunRequest()
    schedule = service.request_run(
        name,
        body.start_from,
        body.stop_after,
        body.input_versions,
        body.promote,
        body.run_at,
        body.on_failure,
    )
    return service.get_schedule_status(name, schedule.id)


@app.get("/workflows/{name}/schedules/{schedule_id}", response_model=ScheduleResponse)
def get_schedule_status(name: str, schedule_id: int, service: WorkflowService = Depends(get_service)):
    return service.get_schedule_status(name, schedule_id)


@app.get("/workflows/{name}/schedules", response_model=list[ScheduleResponse])
def list_pending_schedules(name: str, service: WorkflowService = Depends(get_service)):
    return service.list_pending_schedules(name)


@app.post(
    "/workflows/{name}/recurring-schedules", response_model=RecurringScheduleResponse, status_code=201
)
def create_recurring_schedule(
    name: str, body: CreateRecurringScheduleRequest, service: WorkflowService = Depends(get_service)
):
    return service.create_recurring_schedule(
        name,
        body.cron_expression,
        body.start_from,
        body.stop_after,
        body.input_versions,
        body.promote,
        body.on_failure,
    )


@app.get("/workflows/{name}/recurring-schedules", response_model=list[RecurringScheduleResponse])
def list_recurring_schedules(name: str, service: WorkflowService = Depends(get_service)):
    return service.list_recurring_schedules(name)


@app.post("/workflows/{name}/recurring-schedules/{recurring_schedule_id}/cancel", status_code=204)
def cancel_recurring_schedule(
    name: str, recurring_schedule_id: int, service: WorkflowService = Depends(get_service)
) -> None:
    service.cancel_recurring_schedule(name, recurring_schedule_id)


@app.get("/workflows/{name}/runs", response_model=list[WorkflowRunResponse])
def list_runs(name: str, limit: int = 50, service: WorkflowService = Depends(get_service)):
    return service.list_runs(name, limit)


@app.get("/workflows/{name}/runs/{run_id}", response_model=WorkflowRunResponse)
def get_run(name: str, run_id: int, service: WorkflowService = Depends(get_service)):
    return service.get_run(name, run_id)


@app.post("/workflows/{name}/runs/{run_id}/cancel", status_code=204)
def request_cancel(name: str, run_id: int, service: WorkflowService = Depends(get_service)) -> None:
    service.request_cancel(name, run_id)


@app.get("/workflows/{name}/runs/{run_id}/stage-runs", response_model=list[StageRunResponse])
def list_stage_runs_for_run(name: str, run_id: int, service: WorkflowService = Depends(get_service)):
    return service.list_stage_runs_for_run(name, run_id)


@app.get("/workflows/{name}/stage-runs/{stage_run_id}", response_model=StageRunResponse)
def get_stage_run(name: str, stage_run_id: int, service: WorkflowService = Depends(get_service)):
    return service.get_stage_run(name, stage_run_id)


@app.post("/workflows/{name}/stage-runs/{stage_run_id}/start", status_code=204)
def start_stage_run(name: str, stage_run_id: int, service: WorkflowService = Depends(get_service)) -> None:
    service.start_stage_run(name, stage_run_id)


@app.post("/workflows/{name}/stage-runs/{stage_run_id}/complete", status_code=204)
def complete_stage_run(
    name: str,
    stage_run_id: int,
    body: CompleteStageRunRequest,
    service: WorkflowService = Depends(get_service),
) -> None:
    service.complete_stage_run(name, stage_run_id, body.output_version, body.attempts)


@app.post("/workflows/{name}/stage-runs/{stage_run_id}/fail", status_code=204)
def fail_stage_run(
    name: str,
    stage_run_id: int,
    body: FailStageRunRequest,
    service: WorkflowService = Depends(get_service),
) -> None:
    service.fail_stage_run(name, stage_run_id, body.error, body.attempts)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
