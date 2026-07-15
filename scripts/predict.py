from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401
from stock_forecast.config import DEFAULT_CSV_PATH
from stock_forecast.inference import predict_next_close_from_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict the next trading day's close price.")
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--model", choices=["rnn", "lstm", "best"], default="best")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_name, prediction = predict_next_close_from_csv(args.input, args.model)
    print(
        {
            "model": model_name,
            "input": str(args.input),
            "prediction_next_close": float(np.round(prediction, 4)),
        }
    )


if __name__ == "__main__":
    main()
