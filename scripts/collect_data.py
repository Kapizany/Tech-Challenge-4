from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from stock_forecast.config import (
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    DEFAULT_SYMBOL,
    ensure_project_dirs,
)
from stock_forecast.collection import collect_price_history


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download historical stock prices.")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--end", default=DEFAULT_END_DATE)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--upload-s3", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_project_dirs()

    result = collect_price_history(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        output=args.output,
        upload_s3=args.upload_s3,
    )
    print(f"Saved {result.rows} rows to {result.local_path}")
    if result.s3_bucket and result.s3_key:
        print(f"Uploaded to s3://{result.s3_bucket}/{result.s3_key}")


if __name__ == "__main__":
    main()
