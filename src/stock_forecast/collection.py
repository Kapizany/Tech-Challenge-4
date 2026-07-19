from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yfinance as yf

from stock_forecast.data import normalize_symbol, save_price_csv, symbol_price_csv_path
from stock_forecast.storage import s3_location_for_path, s3_object_exists, upload_to_s3


@dataclass(frozen=True)
class CollectionResult:
    symbol: str
    start: str
    end: str
    rows: int
    local_path: Path
    s3_bucket: str | None = None
    s3_key: str | None = None
    s3_uploaded: bool = False
    s3_object_already_exists: bool = False


def collect_price_history(
    symbol: str,
    start: str,
    end: str,
    output: Path | None = None,
    upload_s3: bool = True,
) -> CollectionResult:
    normalized_symbol = normalize_symbol(symbol)
    output_path = output or symbol_price_csv_path(normalized_symbol)

    df = yf.download(
        normalized_symbol,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        raise RuntimeError(
            f"No data returned by Yahoo Finance for {normalized_symbol} "
            f"between {start} and {end}."
        )

    df = df.reset_index()
    if getattr(df.columns, "nlevels", 1) > 1:
        df.columns = [column[0] for column in df.columns]

    saved_path = save_price_csv(df, output_path)
    s3_bucket = None
    s3_key = None
    s3_uploaded = False
    s3_object_already_exists = False
    if upload_s3:
        s3_bucket, s3_key = s3_location_for_path(saved_path)
        if s3_bucket:
            s3_object_already_exists = s3_object_exists(s3_bucket, s3_key)
            if not s3_object_already_exists:
                upload_to_s3(source=saved_path, bucket=s3_bucket, key=s3_key)
                s3_uploaded = True

    return CollectionResult(
        symbol=normalized_symbol,
        start=start,
        end=end,
        rows=len(df),
        local_path=saved_path,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        s3_uploaded=s3_uploaded,
        s3_object_already_exists=s3_object_already_exists,
    )
