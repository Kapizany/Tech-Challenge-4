from __future__ import annotations

from pathlib import Path

from stock_forecast.tensorflow_runtime import configure_tensorflow_runtime

configure_tensorflow_runtime()

from tensorflow import keras

from stock_forecast.artifacts import (
    LSTM_BUNDLE_PATH,
    ModelName,
    RNN_BUNDLE_PATH,
    load_joblib,
    resolve_model_name,
)
from stock_forecast.data import load_price_csv, normalize_price_frame


def predict_sequence_model_from_frame(df, bundle_path: Path) -> float:
    df = normalize_price_frame(df)
    bundle = load_joblib(bundle_path)
    model = keras.models.load_model(bundle["model_path"])
    window_size = bundle["window_size"]
    feature_columns = bundle["feature_columns"]

    if len(df) < window_size:
        raise ValueError(f"Model needs at least {window_size} rows, got {len(df)}.")

    recent = df.tail(window_size)[feature_columns]
    scaled = bundle["feature_scaler"].transform(recent)
    x = scaled.reshape(1, window_size, len(feature_columns))
    prediction_scaled = model.predict(x, verbose=0).reshape(-1, 1)
    prediction = bundle["target_scaler"].inverse_transform(prediction_scaled).reshape(-1)[0]
    return float(prediction)


def predict_rnn_from_frame(df) -> float:
    return predict_sequence_model_from_frame(df, RNN_BUNDLE_PATH)


def predict_lstm_from_frame(df) -> float:
    return predict_sequence_model_from_frame(df, LSTM_BUNDLE_PATH)


def predict_next_close_from_frame(df, model_name: ModelName) -> tuple[str, float]:
    resolved = resolve_model_name(model_name)
    if resolved == "rnn":
        return resolved, predict_rnn_from_frame(df)
    if resolved == "lstm":
        return resolved, predict_lstm_from_frame(df)
    raise ValueError(f"Unsupported model: {model_name}")


def predict_next_close_from_csv(csv_path: Path, model_name: ModelName) -> tuple[str, float]:
    return predict_next_close_from_frame(load_price_csv(csv_path), model_name)
