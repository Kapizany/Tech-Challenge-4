from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from stock_forecast.config import DATA_DIR, MODELS_DIR, PROJECT_ROOT, REPORTS_DIR

DATA_BUCKET_ENV_NAMES = ("DATA_S3_BUCKET", "STOCK_DATA_S3_BUCKET", "S3_DATA_BUCKET")
MODELS_BUCKET_ENV_NAMES = ("MODELS_S3_BUCKET", "STOCK_MODELS_S3_BUCKET", "S3_MODELS_BUCKET")


def _first_env_value(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _path_kind(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(DATA_DIR.resolve()):
        return "data"
    if resolved.is_relative_to(MODELS_DIR.resolve()) or resolved.is_relative_to(
        REPORTS_DIR.resolve()
    ):
        return "models"
    return "unknown"


def _bucket_and_prefix_for_path(path: Path) -> tuple[str | None, str]:
    kind = _path_kind(path)
    if kind == "data":
        return _first_env_value(DATA_BUCKET_ENV_NAMES), os.getenv("DATA_S3_PREFIX", "")
    if kind == "models":
        return _first_env_value(MODELS_BUCKET_ENV_NAMES), os.getenv("MODELS_S3_PREFIX", "")
    return None, ""


def configured_data_s3_location() -> tuple[str | None, str]:
    return _first_env_value(DATA_BUCKET_ENV_NAMES), os.getenv("DATA_S3_PREFIX", "")


def configured_models_s3_location() -> tuple[str | None, str]:
    return _first_env_value(MODELS_BUCKET_ENV_NAMES), os.getenv("MODELS_S3_PREFIX", "")


def s3_key_for_path(path: Path, prefix: str) -> str:
    relative = path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    normalized_prefix = prefix.strip("/")
    if normalized_prefix:
        return f"{normalized_prefix}/{relative}"
    return relative


def s3_location_for_path(path: Path) -> tuple[str | None, str]:
    bucket, prefix = _bucket_and_prefix_for_path(path)
    return bucket, s3_key_for_path(path, prefix)


def ensure_local_file(path: Path, required: bool = True) -> Path:
    path = Path(path)
    if path.exists():
        return path

    bucket, prefix = _bucket_and_prefix_for_path(path)
    if not bucket:
        if required:
            raise FileNotFoundError(
                f"File not found locally and no S3 bucket is configured for {path}. "
                "Set DATA_S3_BUCKET for data files or MODELS_S3_BUCKET for models/reports."
            )
        return path

    key = s3_key_for_path(path, prefix)
    download_from_s3(bucket=bucket, key=key, destination=path)
    return path


def _boto3_client(service_name: str) -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for S3 operations. Install project dependencies with "
            "`pip install -e .`."
        ) from exc
    return boto3.client(service_name)


def download_from_s3(bucket: str, key: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    client = _boto3_client("s3")
    try:
        client.download_file(bucket, key, str(destination))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download s3://{bucket}/{key} to {destination}: {exc}"
        ) from exc
    return destination


def upload_to_s3(source: Path, bucket: str, key: str) -> str:
    client = _boto3_client("s3")
    try:
        client.upload_file(str(source), bucket, key)
    except Exception as exc:
        raise RuntimeError(f"Failed to upload {source} to s3://{bucket}/{key}: {exc}") from exc
    return key


def s3_object_exists(bucket: str, key: str) -> bool:
    client = _boto3_client("s3")
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        error = getattr(exc, "response", {}).get("Error", {})
        if error.get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise RuntimeError(f"Failed to check s3://{bucket}/{key}: {exc}") from exc


def upload_path_to_configured_s3(source: Path) -> tuple[str | None, str | None]:
    bucket, key = s3_location_for_path(source)
    if not bucket:
        return None, None
    upload_to_s3(source=source, bucket=bucket, key=key)
    return bucket, key


def list_s3_keys(bucket: str, prefix: str = "") -> list[str]:
    client = _boto3_client("s3")
    paginator = client.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys


def delete_s3_key_versions(bucket: str, key: str) -> int:
    client = _boto3_client("s3")
    deleted_count = 0

    paginator = client.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, Prefix=key):
        objects = [
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for item in page.get("Versions", [])
            if item["Key"] == key
        ]
        objects.extend(
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for item in page.get("DeleteMarkers", [])
            if item["Key"] == key
        )
        if not objects:
            continue

        response = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": objects, "Quiet": True},
        )
        deleted_count += len(objects) - len(response.get("Errors", []))

    return deleted_count


def delete_s3_prefix_versions(bucket: str, prefix: str) -> int:
    client = _boto3_client("s3")
    deleted_count = 0

    paginator = client.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for item in page.get("Versions", [])
        ]
        objects.extend(
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for item in page.get("DeleteMarkers", [])
        )
        if not objects:
            continue

        for index in range(0, len(objects), 1000):
            batch = objects[index : index + 1000]
            response = client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": batch, "Quiet": True},
            )
            deleted_count += len(batch) - len(response.get("Errors", []))

    return deleted_count
