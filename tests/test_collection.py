import pandas as pd

from stock_forecast import collection


def _price_frame():
    return pd.DataFrame(
        {
            "Date": ["2024-07-15", "2024-07-16"],
            "Open": [40.96, 41.10],
            "High": [41.30, 41.45],
            "Low": [40.60, 40.80],
            "Close": [41.12, 41.28],
            "Volume": [31200000, 30500000],
        }
    )


def test_collect_price_history_skips_upload_when_s3_object_exists(monkeypatch, tmp_path):
    upload_calls = []

    monkeypatch.setattr(collection.yf, "download", lambda *args, **kwargs: _price_frame())
    monkeypatch.setattr(
        collection,
        "s3_location_for_path",
        lambda path: ("bucket", "data/raw/PETR4.SA/PETR4.SA.csv"),
    )
    monkeypatch.setattr(collection, "s3_object_exists", lambda bucket, key: True)
    monkeypatch.setattr(
        collection,
        "upload_to_s3",
        lambda **kwargs: upload_calls.append(kwargs),
    )

    result = collection.collect_price_history(
        symbol="petr4.sa",
        start="2024-07-15",
        end="2024-07-17",
        output=tmp_path / "PETR4.SA.csv",
    )

    assert result.s3_bucket == "bucket"
    assert result.s3_key == "data/raw/PETR4.SA/PETR4.SA.csv"
    assert result.s3_object_already_exists is True
    assert result.s3_uploaded is False
    assert upload_calls == []


def test_collect_price_history_uploads_when_s3_object_is_missing(monkeypatch, tmp_path):
    upload_calls = []

    monkeypatch.setattr(collection.yf, "download", lambda *args, **kwargs: _price_frame())
    monkeypatch.setattr(
        collection,
        "s3_location_for_path",
        lambda path: ("bucket", "data/raw/PETR4.SA/PETR4.SA.csv"),
    )
    monkeypatch.setattr(collection, "s3_object_exists", lambda bucket, key: False)
    monkeypatch.setattr(
        collection,
        "upload_to_s3",
        lambda **kwargs: upload_calls.append(kwargs),
    )

    result = collection.collect_price_history(
        symbol="PETR4.SA",
        start="2024-07-15",
        end="2024-07-17",
        output=tmp_path / "PETR4.SA.csv",
    )

    assert result.s3_uploaded is True
    assert result.s3_object_already_exists is False
    assert len(upload_calls) == 1
