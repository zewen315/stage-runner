"""FastAPI app exposing ResourceStoreService over HTTP.

Backed by in-memory adapters for now -- swapping in real Postgres/MinIO
adapters only means changing what get_service() constructs; no route
changes. Domain exceptions (ResourceNotFoundError,
ResourceAlreadyExistsError) are translated to HTTP status codes here, at
the boundary, so the service layer stays free of HTTP concerns.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from errors import ResourceAlreadyExistsError, ResourceNotFoundError
from memory import InMemoryBlobStore, InMemoryMetadataRepository
from service import ResourceStoreService

app = FastAPI(title="Resource Store")

_service = ResourceStoreService(InMemoryMetadataRepository(), InMemoryBlobStore())


def get_service() -> ResourceStoreService:
    return _service


@app.exception_handler(ResourceNotFoundError)
async def handle_not_found(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ResourceAlreadyExistsError)
async def handle_already_exists(request: Request, exc: ResourceAlreadyExistsError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


# -- request/response models --------------------------------------------


class CreateResourceRequest(BaseModel):
    name: str


class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    current_version_id: int | None


class UploadVersionRequest(BaseModel):
    value: Any


class ResourceVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    version: int
    storage_uri: str
    created_at: str


class UpdateDependenciesRequest(BaseModel):
    depends_on: list[tuple[str, int]]


class PromoteRequest(BaseModel):
    version: int


class ResourceSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: ResourceVersionResponse
    value: Any


# -- routes ---------------------------------------------------------------


@app.post("/resources", response_model=ResourceResponse, status_code=201)
def create_resource(
    body: CreateResourceRequest, service: ResourceStoreService = Depends(get_service)
):
    return service.create_resource(body.name)


@app.post("/resources/{name}/versions", response_model=ResourceVersionResponse, status_code=201)
def upload_version(
    name: str, body: UploadVersionRequest, service: ResourceStoreService = Depends(get_service)
):
    return service.upload_version(name, body.value)


@app.put("/resources/{name}/versions/{version}/dependencies", status_code=204)
def update_dependencies(
    name: str,
    version: int,
    body: UpdateDependenciesRequest,
    service: ResourceStoreService = Depends(get_service),
) -> None:
    service.update_dependencies(name, version, body.depends_on)


@app.post("/resources/{name}/promotions", status_code=204)
def promote(
    name: str, body: PromoteRequest, service: ResourceStoreService = Depends(get_service)
) -> None:
    service.promote(name, body.version)


@app.get("/resources/{name}", response_model=ResourceSnapshotResponse)
def get_current(name: str, service: ResourceStoreService = Depends(get_service)):
    return service.get(name)


@app.get("/resources/{name}/versions/{version}", response_model=ResourceSnapshotResponse)
def get_version(name: str, version: int, service: ResourceStoreService = Depends(get_service)):
    return service.get(name, version)


@app.get("/resources/{name}/versions/{version}/dependencies", response_model=list[ResourceVersionResponse])
def get_dependencies(name: str, version: int, service: ResourceStoreService = Depends(get_service)):
    return service.dependencies(name, version)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
