from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import optuna
from sklearn.preprocessing import MinMaxScaler

import _bootstrap  # noqa: F401
from stock_forecast.tensorflow_runtime import configure_tensorflow_runtime

configure_tensorflow_runtime()

from tensorflow import keras

from stock_forecast.artifacts import LSTM_BUNDLE_PATH, LSTM_MODEL_PATH, update_model_metrics
from stock_forecast.config import DEFAULT_CSV_PATH, ensure_project_dirs
from stock_forecast.data import load_price_csv, temporal_train_validation_test_split
from stock_forecast.features import LSTM_FEATURE_COLUMNS, make_lstm_sequences
from stock_forecast.metrics import regression_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train and tune the required LSTM model.")
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    keras.utils.set_random_seed(seed)


def build_model(
    window_size: int,
    n_features: int,
    units: int,
    layers: int,
    dropout: float,
    learning_rate: float,
) -> keras.Model:
    model = keras.Sequential(name="petrobras_lstm_forecaster")
    model.add(keras.Input(shape=(window_size, n_features)))
    for layer_index in range(layers):
        return_sequences = layer_index < layers - 1
        model.add(keras.layers.LSTM(units=units, return_sequences=return_sequences))
        if dropout > 0:
            model.add(keras.layers.Dropout(dropout))
    model.add(keras.layers.Dense(1))
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
        loss="mse",
        metrics=[keras.metrics.MeanAbsoluteError(name="mae")],
    )
    return model


def prepare_arrays(csv_path: Path, window_size: int) -> dict[str, np.ndarray | MinMaxScaler]:
    df = load_price_csv(csv_path)
    train_df, validation_df, test_df = temporal_train_validation_test_split(df)

    feature_scaler = MinMaxScaler()
    target_scaler = MinMaxScaler()

    feature_scaler.fit(train_df[LSTM_FEATURE_COLUMNS])
    target_scaler.fit(train_df[["Close"]])

    train_features = feature_scaler.transform(train_df[LSTM_FEATURE_COLUMNS])
    validation_features = feature_scaler.transform(validation_df[LSTM_FEATURE_COLUMNS])
    test_features = feature_scaler.transform(test_df[LSTM_FEATURE_COLUMNS])

    train_target = target_scaler.transform(train_df[["Close"]]).reshape(-1)
    validation_target = target_scaler.transform(validation_df[["Close"]]).reshape(-1)
    test_target = target_scaler.transform(test_df[["Close"]]).reshape(-1)

    x_train, y_train = make_lstm_sequences(train_features, train_target, window_size)
    x_validation, y_validation = make_lstm_sequences(
        validation_features, validation_target, window_size
    )
    x_test, y_test = make_lstm_sequences(test_features, test_target, window_size)

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


def objective_factory(csv_path: Path, seed: int):
    def objective(trial: optuna.Trial) -> float:
        set_seed(seed)
        window_size = trial.suggest_categorical("window_size", [20, 30, 45, 60])
        units = trial.suggest_categorical("units", [32, 64, 96, 128])
        layers = trial.suggest_int("layers", 1, 3)
        dropout = trial.suggest_float("dropout", 0.0, 0.4, step=0.1)
        learning_rate = trial.suggest_float("learning_rate", 1e-4, 5e-3, log=True)
        batch_size = trial.suggest_categorical("batch_size", [16, 32, 64])
        max_epochs = trial.suggest_int("epochs", 40, 160, step=20)

        arrays = prepare_arrays(csv_path, window_size)
        model = build_model(
            window_size=window_size,
            n_features=len(LSTM_FEATURE_COLUMNS),
            units=units,
            layers=layers,
            dropout=dropout,
            learning_rate=learning_rate,
        )
        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=12,
                restore_best_weights=True,
            )
        ]
        history = model.fit(
            arrays["x_train"],
            arrays["y_train"],
            validation_data=(arrays["x_validation"], arrays["y_validation"]),
            epochs=max_epochs,
            batch_size=batch_size,
            verbose=0,
            callbacks=callbacks,
        )
        return float(min(history.history["val_loss"]))

    return objective


def main() -> None:
    args = parse_args()
    ensure_project_dirs()
    set_seed(args.seed)

    study = optuna.create_study(direction="minimize", study_name="petrobras_lstm")
    study.optimize(objective_factory(args.input, args.seed), n_trials=args.trials)

    best = study.best_params
    arrays = prepare_arrays(args.input, best["window_size"])
    model = build_model(
        window_size=best["window_size"],
        n_features=len(LSTM_FEATURE_COLUMNS),
        units=best["units"],
        layers=best["layers"],
        dropout=best["dropout"],
        learning_rate=best["learning_rate"],
    )
    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=15,
            restore_best_weights=True,
        )
    ]
    history = model.fit(
        arrays["x_train"],
        arrays["y_train"],
        validation_data=(arrays["x_validation"], arrays["y_validation"]),
        epochs=best["epochs"],
        batch_size=best["batch_size"],
        verbose=1,
        callbacks=callbacks,
    )

    validation_pred_scaled = model.predict(arrays["x_validation"], verbose=0).reshape(-1, 1)
    test_pred_scaled = model.predict(arrays["x_test"], verbose=0).reshape(-1, 1)
    validation_pred = arrays["target_scaler"].inverse_transform(validation_pred_scaled).reshape(-1)
    test_pred = arrays["target_scaler"].inverse_transform(test_pred_scaled).reshape(-1)
    validation_true = arrays["target_scaler"].inverse_transform(
        arrays["y_validation"].reshape(-1, 1)
    ).reshape(-1)
    test_true = arrays["target_scaler"].inverse_transform(arrays["y_test"].reshape(-1, 1)).reshape(
        -1
    )

    model.save(LSTM_MODEL_PATH)
    import joblib

    joblib.dump(
        {
            "feature_scaler": arrays["feature_scaler"],
            "target_scaler": arrays["target_scaler"],
            "feature_columns": LSTM_FEATURE_COLUMNS,
            "window_size": best["window_size"],
            "best_params": best,
            "model_path": str(LSTM_MODEL_PATH),
        },
        LSTM_BUNDLE_PATH,
    )

    payload = {
        "best_params": best,
        "validation_metrics": regression_metrics(validation_true, validation_pred),
        "test_metrics": regression_metrics(test_true, test_pred),
        "epochs_ran": len(history.history["loss"]),
        "artifact_paths": {
            "model": str(LSTM_MODEL_PATH),
            "bundle": str(LSTM_BUNDLE_PATH),
        },
    }
    update_model_metrics("lstm", payload)
    print(payload)


if __name__ == "__main__":
    main()
