from __future__ import annotations

from pathlib import Path
from typing import Literal

import joblib

from stock_forecast.config import BEST_MODEL_PATH, METRICS_PATH, MODELS_DIR
from stock_forecast.metrics import read_json, write_json

ModelName = Literal["rnn", "lstm", "best"]
SUPPORTED_MODEL_NAMES = {"rnn", "lstm"}

RNN_MODEL_PATH = MODELS_DIR / "rnn.keras"
RNN_BUNDLE_PATH = MODELS_DIR / "rnn_bundle.joblib"
LSTM_MODEL_PATH = MODELS_DIR / "lstm.keras"
LSTM_BUNDLE_PATH = MODELS_DIR / "lstm_bundle.joblib"


def save_joblib(payload: object, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, path)
    return path


def load_joblib(path: Path) -> object:
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    return joblib.load(path)


def update_model_metrics(model_name: str, payload: dict) -> dict:
    metrics = read_json(METRICS_PATH, default={})
    metrics[model_name] = payload
    write_json(METRICS_PATH, metrics)
    update_best_model(metrics)
    return metrics


def update_best_model(metrics: dict) -> str | None:
    candidates = {
        name: payload
        for name, payload in metrics.items()
        if name in SUPPORTED_MODEL_NAMES
        and isinstance(payload, dict)
        and "test_metrics" in payload
    }
    if not candidates:
        return None

    best_name = min(
        candidates,
        key=lambda name: float(candidates[name]["test_metrics"].get("rmse", float("inf"))),
    )
    write_json(BEST_MODEL_PATH, {"best_model": best_name})
    return best_name


def resolve_model_name(model_name: ModelName) -> str:
    if model_name != "best":
        return model_name
    best_payload = read_json(BEST_MODEL_PATH, default={})
    best = best_payload.get("best_model")
    if best not in SUPPORTED_MODEL_NAMES:
        raise FileNotFoundError(
            "Best model is not available yet. Train at least one model first."
        )
    return best
