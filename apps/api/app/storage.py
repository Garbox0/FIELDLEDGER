import os
from functools import lru_cache
from io import BytesIO

import urllib3
from minio import Minio


class ObjectStorage:
    def __init__(self) -> None:
        self.bucket = os.getenv("MINIO_BUCKET", "fieldledger-documents")
        self.client = Minio(
            os.getenv("MINIO_ENDPOINT", "minio:9000"),
            access_key=os.environ["MINIO_ROOT_USER"],
            secret_key=os.environ["MINIO_ROOT_PASSWORD"],
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            http_client=urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=2.0, read=5.0), retries=False
            ),
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_bytes(
        self, object_key: str, content: bytes, content_type: str, sha256_hash: str
    ) -> None:
        self.ensure_bucket()
        self.client.put_object(
            self.bucket,
            object_key,
            BytesIO(content),
            len(content),
            content_type=content_type,
            metadata={"sha256": sha256_hash},
        )

    def remove(self, object_key: str) -> None:
        self.client.remove_object(self.bucket, object_key)


@lru_cache
def get_storage() -> ObjectStorage:
    return ObjectStorage()
