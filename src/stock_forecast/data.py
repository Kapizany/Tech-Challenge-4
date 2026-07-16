from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_forecast.config import OHLCV_COLUMNS, SplitRatios
from stock_forecast.storage import ensure_local_file


def load_price_csv(path: Path) -> pd.DataFrame:
    ensure_local_file(path)
    df = pd.read_csv(path, parse_dates=["Date"])
    return normalize_price_frame(df)


def normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    if "Date" not in normalized.columns:
        normalized = normalized.reset_index()
        if "index" in normalized.columns and "Date" not in normalized.columns:
            normalized = normalized.rename(columns={"index": "Date"})

    missing = [column for column in ["Date", *OHLCV_COLUMNS] if column not in normalized.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
    normalized = normalized.dropna(subset=["Date", "Close"]).sort_values("Date")
    normalized = normalized.drop_duplicates(subset=["Date"], keep="last")

    for column in OHLCV_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.dropna(subset=OHLCV_COLUMNS)
    return normalized[["Date", *OHLCV_COLUMNS]].reset_index(drop=True)


def temporal_train_validation_test_split(
    df: pd.DataFrame, ratios: SplitRatios = SplitRatios()
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ratios.validate()
    if len(df) < 30:
        raise ValueError("At least 30 rows are required for a temporal split.")

    train_end = int(len(df) * ratios.train)
    validation_end = int(len(df) * (ratios.train + ratios.validation))
    return (
        df.iloc[:train_end].copy(),
        df.iloc[train_end:validation_end].copy(),
        df.iloc[validation_end:].copy(),
    )


def save_price_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_price_frame(df)
    normalized.to_csv(path, index=False)
    return path
