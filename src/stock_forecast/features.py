from __future__ import annotations

import numpy as np
import pandas as pd

from stock_forecast.config import OHLCV_COLUMNS


LSTM_FEATURE_COLUMNS = OHLCV_COLUMNS

SEQUENCE_FEATURE_COLUMNS = LSTM_FEATURE_COLUMNS


def make_lstm_sequences(
    values: np.ndarray, target_values: np.ndarray, window_size: int
) -> tuple[np.ndarray, np.ndarray]:
    if window_size <= 0:
        raise ValueError("window_size must be positive.")
    if len(values) != len(target_values):
        raise ValueError("Feature and target arrays must have the same length.")
    if len(values) <= window_size:
        raise ValueError(
            f"Need more rows than the LSTM window_size={window_size}; got {len(values)}."
        )

    x, y = [], []
    for index in range(window_size, len(values)):
        x.append(values[index - window_size : index])
        y.append(target_values[index])
    return np.asarray(x, dtype=np.float32), np.asarray(y, dtype=np.float32)


def make_sequence_sequences(
    values: np.ndarray, target_values: np.ndarray, window_size: int
) -> tuple[np.ndarray, np.ndarray]:
    return make_lstm_sequences(values, target_values, window_size)
