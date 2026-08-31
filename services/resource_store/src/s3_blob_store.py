"""S3-compatible BlobStore, used against MinIO in docker-compose (and,
unchanged, against real AWS S3 later -- MinIO speaks the S3 API).

Values are JSON-encoded before upload; BlobStore's contract (put/get by
storage_uri) doesn't care what the bytes mean, only this adapter does.
"""

from __future__ import annotations

import json
from typing import Any

import boto3


class S3BlobStore:
    def __init__(self, *, bucket: str, endpoint_url: str, access_key: str, secret_key: str):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        existing = {b["Name"] for b in self._client.list_buckets().get("Buckets", [])}
        if self._bucket not in existing:
            self._client.create_bucket(Bucket=self._bucket)

    def put(self, storage_uri: str, value: Any) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=storage_uri, Body=json.dumps(value).encode("utf-8")
        )

    def get(self, storage_uri: str) -> Any:
        response = self._client.get_object(Bucket=self._bucket, Key=storage_uri)
        return json.loads(response["Body"].read())
