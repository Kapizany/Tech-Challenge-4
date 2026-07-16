import sys
from types import SimpleNamespace

import pytest

from stock_forecast import storage


def test_ensure_local_file_returns_existing_file(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("ok", encoding="utf-8")

    assert storage.ensure_local_file(path) == path


def test_ensure_local_file_raises_without_bucket(tmp_path, monkeypatch):
    path = tmp_path / "missing.csv"
    monkeypatch.delenv("DATA_S3_BUCKET", raising=False)
    monkeypatch.delenv("MODELS_S3_BUCKET", raising=False)

    with pytest.raises(FileNotFoundError):
        storage.ensure_local_file(path)


def test_ensure_local_file_downloads_missing_data_from_s3(tmp_path, monkeypatch):
    project_root = tmp_path
    data_dir = project_root / "data"
    destination = data_dir / "raw" / "PETR4.SA.csv"
    calls = []

    class FakeS3Client:
        def download_file(self, bucket, key, filename):
            calls.append((bucket, key, filename))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")

    fake_boto3 = SimpleNamespace(client=lambda service: FakeS3Client())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setattr(storage, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "MODELS_DIR", project_root / "models")
    monkeypatch.setattr(storage, "REPORTS_DIR", project_root / "reports")
    monkeypatch.setenv("DATA_S3_BUCKET", "data-bucket")
    monkeypatch.setenv("DATA_S3_PREFIX", "tech-challenge")

    storage.ensure_local_file(destination)

    assert calls == [
        (
            "data-bucket",
            "tech-challenge/data/raw/PETR4.SA.csv",
            str(destination),
        )
    ]
    assert destination.exists()
