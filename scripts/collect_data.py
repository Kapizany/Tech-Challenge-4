from __future__ import annotations

import argparse
from pathlib import Path

import yfinance as yf

import _bootstrap  # noqa: F401
from stock_forecast.config import (
    DEFAULT_CSV_PATH,
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    DEFAULT_SYMBOL,
    ensure_project_dirs,
)
from stock_forecast.data import save_price_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download historical stock prices.")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--end", default=DEFAULT_END_DATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_CSV_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_project_dirs()

    df = yf.download(
        args.symbol,
        start=args.start,
        end=args.end,
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        raise RuntimeError(
            f"No data returned by Yahoo Finance for {args.symbol} "
            f"between {args.start} and {args.end}."
        )

    df = df.reset_index()
    if isinstance(df.columns, type(df.columns)) and getattr(df.columns, "nlevels", 1) > 1:
        df.columns = [column[0] for column in df.columns]

    output = save_price_csv(df, args.output)
    print(f"Saved {len(df)} rows to {output}")


if __name__ == "__main__":
    main()
