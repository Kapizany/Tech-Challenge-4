from __future__ import annotations

import argparse
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.preprocessing import MinMaxScaler

import _bootstrap  # noqa: F401
from stock_forecast.tensorflow_runtime import configure_tensorflow_runtime

configure_tensorflow_runtime()

from tensorflow import keras

from stock_forecast.artifacts import (
    LSTM_BUNDLE_PATH,
    LSTM_MODEL_PATH,
    RNN_BUNDLE_PATH,
    RNN_MODEL_PATH,
    update_model_metrics,
)
from stock_forecast.config import DEFAULT_CSV_PATH, ensure_project_dirs
from stock_forecast.data import load_price_csv, temporal_train_validation_test_split
from stock_forecast.features import SEQUENCE_FEATURE_COLUMNS, make_sequence_sequences
from stock_forecast.metrics import regression_metrics, write_json


@dataclass(frozen=True)
class Architecture:
    name: str
    model_type: str
    window_size: int
    units: tuple[int, ...]
    dropout: float
    learning_rate: float
    batch_size: int


ARCHITECTURES = [
    Architecture("rnn_simple_30", "rnn", 30, (32,), 0.0, 1e-3, 32),
    Architecture("rnn_stacked_45", "rnn", 45, (64, 32), 0.2, 8e-4, 32),
    Architecture("rnn_wide_60", "rnn", 60, (96,), 0.2, 8e-4, 16),
    Architecture("lstm_simple_30", "lstm", 30, (32,), 0.0, 1e-3, 32),
    Architecture("lstm_stacked_45", "lstm", 45, (64, 32), 0.2, 8e-4, 32),
    Architecture("lstm_wide_60", "lstm", 60, (96,), 0.2, 8e-4, 16),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train and compare classic RNN and LSTM architectures."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--architectures",
        nargs="+",
        choices=[architecture.name for architecture in ARCHITECTURES],
        default=[architecture.name for architecture in ARCHITECTURES],
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    keras.utils.set_random_seed(seed)


def prepare_arrays(csv_path: Path, window_size: int) -> dict[str, np.ndarray | MinMaxScaler]:
    df = load_price_csv(csv_path)
    train_df, validation_df, test_df = temporal_train_validation_test_split(df)

    feature_scaler = MinMaxScaler()
    target_scaler = MinMaxScaler()
    feature_scaler.fit(train_df[SEQUENCE_FEATURE_COLUMNS])
    target_scaler.fit(train_df[["Close"]])

    train_features = feature_scaler.transform(train_df[SEQUENCE_FEATURE_COLUMNS])
    validation_features = feature_scaler.transform(validation_df[SEQUENCE_FEATURE_COLUMNS])
    test_features = feature_scaler.transform(test_df[SEQUENCE_FEATURE_COLUMNS])

    train_target = target_scaler.transform(train_df[["Close"]]).reshape(-1)
    validation_target = target_scaler.transform(validation_df[["Close"]]).reshape(-1)
    test_target = target_scaler.transform(test_df[["Close"]]).reshape(-1)

    x_train, y_train = make_sequence_sequences(train_features, train_target, window_size)
    x_validation, y_validation = make_sequence_sequences(
        validation_features, validation_target, window_size
    )
    x_test, y_test = make_sequence_sequences(test_features, test_target, window_size)

    return {
        "x_train": x_train,
        "y_train": y_train,
        "x_validation": x_validation,
        "y_validation": y_validation,
        "x_test": x_test,
        "y_test": y_test,
        "feature_scaler": feature_scaler,
        "target_scaler": target_scaler,
    }


def build_model(architecture: Architecture, n_features: int) -> keras.Model:
    layer_class = keras.layers.SimpleRNN if architecture.model_type == "rnn" else keras.layers.LSTM
    model = keras.Sequential(name=f"petrobras_{architecture.name}")
    model.add(keras.Input(shape=(architecture.window_size, n_features)))
    for index, units in enumerate(architecture.units):
        model.add(layer_class(units=units, return_sequences=index < len(architecture.units) - 1))
        if architecture.dropout > 0:
            model.add(keras.layers.Dropout(architecture.dropout))
    model.add(keras.layers.Dense(1))
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=architecture.learning_rate),
        loss="mse",
        metrics=[keras.metrics.MeanAbsoluteError(name="mae")],
    )
    return model


def inverse_target(target_scaler: MinMaxScaler, values: np.ndarray) -> np.ndarray:
    return target_scaler.inverse_transform(values.reshape(-1, 1)).reshape(-1)


def train_architecture(
    csv_path: Path, architecture: Architecture, epochs: int, patience: int, seed: int
) -> tuple[keras.Model, dict, dict]:
    set_seed(seed)
    arrays = prepare_arrays(csv_path, architecture.window_size)
    model = build_model(architecture, n_features=len(SEQUENCE_FEATURE_COLUMNS))
    history = model.fit(
        arrays["x_train"],
        arrays["y_train"],
        validation_data=(arrays["x_validation"], arrays["y_validation"]),
        epochs=epochs,
        batch_size=architecture.batch_size,
        verbose=1,
        callbacks=[
            keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=patience,
                restore_best_weights=True,
            )
        ],
    )

    validation_pred = inverse_target(
        arrays["target_scaler"], model.predict(arrays["x_validation"], verbose=0)
    )
    test_pred = inverse_target(arrays["target_scaler"], model.predict(arrays["x_test"], verbose=0))
    validation_true = inverse_target(arrays["target_scaler"], arrays["y_validation"])
    test_true = inverse_target(arrays["target_scaler"], arrays["y_test"])

    result = {
        "architecture": asdict(architecture),
        "epochs_ran": len(history.history["loss"]),
        "validation_metrics": regression_metrics(validation_true, validation_pred),
        "test_metrics": regression_metrics(test_true, test_pred),
    }
    bundle = {
        "feature_scaler": arrays["feature_scaler"],
        "target_scaler": arrays["target_scaler"],
        "feature_columns": SEQUENCE_FEATURE_COLUMNS,
        "window_size": architecture.window_size,
        "architecture": asdict(architecture),
    }
    return model, bundle, result


def save_family_winner(model: keras.Model, bundle: dict, model_type: str) -> dict[str, str]:
    if model_type == "rnn":
        model_path = RNN_MODEL_PATH
        bundle_path = RNN_BUNDLE_PATH
    elif model_type == "lstm":
        model_path = LSTM_MODEL_PATH
        bundle_path = LSTM_BUNDLE_PATH
    else:
        raise ValueError(f"Unsupported model_type: {model_type}")

    model.save(model_path)
    bundle = {**bundle, "model_path": str(model_path)}
    joblib.dump(bundle, bundle_path)
    return {"model": str(model_path), "bundle": str(bundle_path)}


def main() -> None:
    args = parse_args()
    ensure_project_dirs()
    selected = [item for item in ARCHITECTURES if item.name in args.architectures]
    all_results = []
    best_by_family = {}

    for architecture in selected:
        model, bundle, result = train_architecture(
            args.input, architecture, args.epochs, args.patience, args.seed
        )
        all_results.append(result)
        model_type = architecture.model_type
        current_best = best_by_family.get(model_type)
        if current_best is None or result["test_metrics"]["rmse"] < current_best["result"][
            "test_metrics"
        ]["rmse"]:
            best_by_family[model_type] = {"model": model, "bundle": bundle, "result": result}

    for model_type, winner in best_by_family.items():
        artifact_paths = save_family_winner(winner["model"], winner["bundle"], model_type)
        family_results = [
            result
            for result in all_results
            if result["architecture"]["model_type"] == model_type
        ]
        payload = {
            "best_architecture": winner["result"]["architecture"],
            "validation_metrics": winner["result"]["validation_metrics"],
            "test_metrics": winner["result"]["test_metrics"],
            "architectures_tested": family_results,
            "artifact_paths": artifact_paths,
        }
        update_model_metrics(model_type, payload)

    write_json(
        Path("reports/recurrent_architecture_comparison.json"),
        {"architectures_tested": all_results},
    )
    print({"trained_architectures": [item.name for item in selected], "results": all_results})


if __name__ == "__main__":
    main()
