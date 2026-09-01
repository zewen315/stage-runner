"""FastAPI app exposing ResourceStoreService over HTTP.

Backed by real Postgres + MinIO when DATABASE_URL is set (docker-compose
sets it), and in-memory adapters otherwise (plain `uvicorn api:app` for
quick local runs, and tests, which override get_service directly anyway).
Validator loading is always the real, file-based one regardless of that --
reading resources/<name>.py from disk isn't a "production only" concern,
same reasoning workflow_service applies to its own workflows/ disk check.
Domain exceptions (ResourceNotFoundError, ResourceAlreadyExistsError,
ResourceValidationError) are translated to HTTP status codes here, at the
boundary, so the service layer stays free of HTTP concerns.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from errors import ResourceAlreadyExistsError, ResourceNotFoundError, ResourceValidationError
from memory import InMemoryBlobStore, InMemoryMetadataRepository
from service import ResourceStoreService
from validator_loader import FileResourceValidatorLoader


def _build_service() -> ResourceStoreService:
    resources_root = Path(os.environ.get("RESOURCES_ROOT", "../../resources")).resolve()
    validators = FileResourceValidatorLoader(resources_root)

    database_url = os.environ.get("DATABASE_URL")
    if database_url is None:
        return ResourceStoreService(InMemoryMetadataRepository(), InMemoryBlobStore(), validators)

    from postgres_repository import PostgresMetadataRepository
    from s3_blob_store import S3BlobStore

    metadata = PostgresMetadataRepository(database_url)
    blobs = S3BlobStore(
        bucket=os.environ.get("BLOB_BUCKET", "resources"),
        endpoint_url=os.environ["BLOB_ENDPOINT_URL"],
        access_key=os.environ["BLOB_ACCESS_KEY"],
        secret_key=os.environ["BLOB_SECRET_KEY"],
    )
    return ResourceStoreService(metadata, blobs, validators)


app = FastAPI(title="Resource Store")

_service = _build_service()


def get_service() -> ResourceStoreService:
    return _service


@app.exception_handler(ResourceNotFoundError)
async def handle_not_found(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ResourceAlreadyExistsError)
async def handle_already_exists(request: Request, exc: ResourceAlreadyExistsError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ResourceValidationError)
async def handle_validation_error(request: Request, exc: ResourceValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


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
    is_test: bool = False


class ResourceVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    version: int
    storage_uri: str
    created_at: str
    is_test: bool


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
    return service.upload_version(name, body.value, body.is_test)


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
