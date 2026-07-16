from __future__ import annotations

import os
from pathlib import Path

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


def _s3_key_for_path(path: Path, prefix: str) -> str:
    relative = path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    normalized_prefix = prefix.strip("/")
    if normalized_prefix:
        return f"{normalized_prefix}/{relative}"
    return relative


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

    key = _s3_key_for_path(path, prefix)
    download_from_s3(bucket=bucket, key=key, destination=path)
    return path


def download_from_s3(bucket: str, key: str, destination: Path) -> Path:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required to download missing artifacts from S3. "
            "Install project dependencies with `pip install -e .`."
        ) from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    client = boto3.client("s3")
    try:
        client.download_file(bucket, key, str(destination))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download s3://{bucket}/{key} to {destination}: {exc}"
        ) from exc
    return destination
