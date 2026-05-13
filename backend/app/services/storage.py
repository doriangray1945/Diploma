"""MinIO S3 storage adapter for catalog product images.

Bucket policy: public read. Backend stores absolute public URLs in
`product_variants.images`; browsers fetch directly from MinIO.

Used at startup (ensure_bucket) and from /tmp seed scripts (upload).
Not on request-path: serving is direct browser → MinIO.
"""
from __future__ import annotations

import json
import logging
from io import BytesIO
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


log = logging.getLogger(__name__)


_PUBLIC_READ_POLICY_TEMPLATE = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": ["arn:aws:s3:::{bucket}/*"],
        }
    ],
}


class MinioStorage:
    def __init__(self) -> None:
        self.endpoint = settings.MINIO_ENDPOINT
        self.public_endpoint = settings.MINIO_PUBLIC_ENDPOINT.rstrip("/")
        self.bucket = settings.MINIO_BUCKET
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchBucket"):
                self._client.create_bucket(Bucket=self.bucket)
            else:
                raise
        # Make bucket public-readable for direct browser access.
        policy = json.dumps(_PUBLIC_READ_POLICY_TEMPLATE).replace("{bucket}", self.bucket)
        self._client.put_bucket_policy(Bucket=self.bucket, Policy=policy)

    def upload_file(self, key: str, data: bytes | BinaryIO, content_type: str = "image/jpeg") -> str:
        if isinstance(data, (bytes, bytearray)):
            data = BytesIO(data)
        self._client.upload_fileobj(
            data, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )
        return self.public_url(key)

    def public_url(self, key: str) -> str:
        return f"{self.public_endpoint}/{self.bucket}/{key.lstrip('/')}"
