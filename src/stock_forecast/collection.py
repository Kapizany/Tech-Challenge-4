from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yfinance as yf

from stock_forecast.data import normalize_symbol, save_price_csv, symbol_price_csv_path
from stock_forecast.storage import upload_path_to_configured_s3


@dataclass(frozen=True)
class CollectionResult:
    symbol: str
    start: str
    end: str
    rows: int
    local_path: Path
    s3_bucket: str | None = None
    s3_key: str | None = None


def collect_price_history(
    symbol: str,
    start: str,
    end: str,
    output: Path | None = None,
    upload_s3: bool = False,
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
    if upload_s3:
        s3_bucket, s3_key = upload_path_to_configured_s3(saved_path)

    return CollectionResult(
        symbol=normalized_symbol,
        start=start,
        end=end,
        rows=len(df),
        local_path=saved_path,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
    )
