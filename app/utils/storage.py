import os
import io
from typing import Optional

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    Minio = None
    S3Error = Exception
    MINIO_AVAILABLE = False


class Storage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        secure: bool = True,
    ):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=secure,
        )
        self.bucket = bucket
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_bytes(self, data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            self.bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_name

    def upload_file(self, filepath: str, object_name: str, content_type: str = "application/octet-stream") -> str:
        with open(filepath, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            self.client.put_object(
                self.bucket, object_name, f, length=size, content_type=content_type
            )
        return object_name

    def download_bytes(self, object_name: str) -> bytes:
        response = self.client.get_object(self.bucket, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data

    def download_file(self, object_name: str, filepath: str):
        self.client.fget_object(self.bucket, object_name, filepath)

    def get_url(self, object_name: str, expires: int = 3600) -> Optional[str]:
        try:
            return self.client.presigned_get_object(self.bucket, object_name, expires=expires)
        except S3Error:
            return None

    def exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket, object_name)
            return True
        except S3Error:
            return False

    def delete(self, object_name: str):
        try:
            self.client.remove_object(self.bucket, object_name)
        except S3Error:
            pass

    def list(self, prefix: str = "") -> list:
        objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return [o.object_name for o in objects]


def init_storage(app):
    if not MINIO_AVAILABLE:
        app.logger.warning("MinIO package not installed, storage disabled")
        app.config["STORAGE"] = None
        app.config["STORAGE_AVAILABLE"] = False
        return

    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    bucket = os.getenv("MINIO_BUCKET", "trading-charts")
    region = os.getenv("MINIO_REGION", "us-east-1")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

    try:
        storage = Storage(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            region=region,
            secure=secure,
        )
        app.config["STORAGE"] = storage
        app.config["STORAGE_AVAILABLE"] = True
    except Exception as e:
        app.logger.warning(f"MinIO unavailable: {e}")
        app.config["STORAGE"] = None
        app.config["STORAGE_AVAILABLE"] = False


def get_storage():
    from flask import current_app
    return current_app.config.get("STORAGE")


def storage_available():
    from flask import current_app
    return current_app.config.get("STORAGE_AVAILABLE", False)
