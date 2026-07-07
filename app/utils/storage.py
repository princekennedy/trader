import os
import io
import shutil
from typing import Optional
from urllib.parse import quote

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    Minio = None
    S3Error = Exception
    MINIO_AVAILABLE = False


class MinioStorage:
    def __init__(self, endpoint, access_key, secret_key, bucket, region="us-east-1", secure=True):
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, region=region, secure=secure)
        self.bucket = bucket
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_bytes(self, data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(self.bucket, object_name, io.BytesIO(data), length=len(data), content_type=content_type)
        return object_name

    def download_bytes(self, object_name: str) -> bytes:
        response = self.client.get_object(self.bucket, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data

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


class LocalStorage:
    def __init__(self, base_path: str, serve_url_prefix: str = "/charts/uploads/"):
        self.base_path = os.path.normpath(base_path)
        self.serve_url_prefix = serve_url_prefix
        os.makedirs(self.base_path, exist_ok=True)

    def _resolve(self, object_name: str) -> str:
        safe = object_name.replace("..", "_").replace("/", os.sep)
        return os.path.normpath(os.path.join(self.base_path, safe))

    def _ensure_dir(self, filepath: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

    def upload_bytes(self, data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        fp = self._resolve(object_name)
        self._ensure_dir(fp)
        with open(fp, "wb") as f:
            f.write(data)
        return object_name

    def download_bytes(self, object_name: str) -> bytes:
        fp = self._resolve(object_name)
        if not os.path.isfile(fp):
            raise FileNotFoundError(f"Object not found: {object_name}")
        with open(fp, "rb") as f:
            return f.read()

    def get_url(self, object_name: str, expires: int = 3600) -> Optional[str]:
        return f"{self.serve_url_prefix}{quote(object_name)}"

    def exists(self, object_name: str) -> bool:
        return os.path.isfile(self._resolve(object_name))

    def delete(self, object_name: str):
        fp = self._resolve(object_name)
        if os.path.isfile(fp):
            os.remove(fp)

    def upload_file(self, filepath: str, object_name: str, content_type: str = "application/octet-stream") -> str:
        fp = self._resolve(object_name)
        self._ensure_dir(fp)
        shutil.copy2(filepath, fp)
        return object_name

    def download_file(self, object_name: str, filepath: str):
        data = self.download_bytes(object_name)
        with open(filepath, "wb") as f:
            f.write(data)


def init_storage(app):
    base_path = os.path.normpath(
        os.getenv("UPLOAD_FOLDER", os.path.join(app.root_path, "..", "uploads"))
    )
    app.config["UPLOAD_FOLDER"] = base_path
    os.makedirs(base_path, exist_ok=True)

    if MINIO_AVAILABLE:
        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        bucket = os.getenv("MINIO_BUCKET", "trading-charts")
        region = os.getenv("MINIO_REGION", "us-east-1")
        secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

        try:
            storage = MinioStorage(
                endpoint=endpoint, access_key=access_key, secret_key=secret_key,
                bucket=bucket, region=region, secure=secure,
            )
            app.config["STORAGE"] = storage
            app.config["STORAGE_AVAILABLE"] = True
            app.config["STORAGE_BACKEND"] = "minio"
            app.logger.info("Storage: MinIO")
            return
        except Exception as e:
            app.logger.warning(f"MinIO unavailable, falling back to local filesystem: {e}")
    else:
        app.logger.info("MinIO package not installed, using local filesystem")

    storage = LocalStorage(base_path=base_path, serve_url_prefix="/charts/uploads/")
    app.config["STORAGE"] = storage
    app.config["STORAGE_AVAILABLE"] = True
    app.config["STORAGE_BACKEND"] = "local"
    app.logger.info(f"Storage: local filesystem ({base_path})")


def get_storage():
    from flask import current_app
    return current_app.config.get("STORAGE")


def storage_available():
    from flask import current_app
    return current_app.config.get("STORAGE_AVAILABLE", False)
