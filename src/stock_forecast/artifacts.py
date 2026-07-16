from __future__ import annotations

from pathlib import Path
from typing import Literal

import joblib

from stock_forecast.config import BEST_MODEL_PATH, METRICS_PATH, MODELS_DIR
from stock_forecast.metrics import read_json, write_json
from stock_forecast.storage import ensure_local_file

ModelName = Literal["rnn", "lstm", "best"]
SUPPORTED_MODEL_NAMES = {"rnn", "lstm"}

RNN_MODEL_PATH = MODELS_DIR / "rnn.keras"
RNN_BUNDLE_PATH = MODELS_DIR / "rnn_bundle.joblib"
LSTM_MODEL_PATH = MODELS_DIR / "lstm.keras"
LSTM_BUNDLE_PATH = MODELS_DIR / "lstm_bundle.joblib"
MODEL_ARTIFACT_PATHS = {
    "rnn": (RNN_MODEL_PATH, RNN_BUNDLE_PATH),
    "lstm": (LSTM_MODEL_PATH, LSTM_BUNDLE_PATH),
}
FALLBACK_MODEL_ORDER = ("lstm", "rnn")


def save_joblib(payload: object, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, path)
    return path


def load_joblib(path: Path) -> object:
    ensure_local_file(path)
    return joblib.load(path)


def update_model_metrics(model_name: str, payload: dict) -> dict:
    metrics = read_json(METRICS_PATH, default={})
    metrics[model_name] = payload
    write_json(METRICS_PATH, metrics)
    update_best_model(metrics)
    return metrics


def should_replace_model(
    model_name: str, payload: dict, metric_name: str = "rmse"
) -> tuple[bool, str]:
    metrics = read_json(METRICS_PATH, default={})
    existing = metrics.get(model_name)
    expected_artifacts = MODEL_ARTIFACT_PATHS.get(model_name, ())
    for path in expected_artifacts:
        ensure_local_file(path, required=False)
    missing_artifacts = [str(path) for path in expected_artifacts if not path.exists()]

    if missing_artifacts:
        return True, f"missing artifacts: {missing_artifacts}"
    if not isinstance(existing, dict) or "test_metrics" not in existing:
        return True, f"no previous metrics found for {model_name}"

    new_metric = float(payload["test_metrics"][metric_name])
    existing_metric = float(existing["test_metrics"].get(metric_name, float("inf")))
    if new_metric < existing_metric:
        return (
            True,
            f"{metric_name} improved from {existing_metric:.6f} to {new_metric:.6f}",
        )
    return (
        False,
        f"{metric_name} did not improve: current best {existing_metric:.6f}, new {new_metric:.6f}",
    )


def model_artifacts_available(model_name: str) -> bool:
    expected_artifacts = MODEL_ARTIFACT_PATHS.get(model_name, ())
    for path in expected_artifacts:
        ensure_local_file(path, required=False)
    return bool(expected_artifacts) and all(path.exists() for path in expected_artifacts)


def available_models_from_artifacts() -> list[str]:
    return [model_name for model_name in FALLBACK_MODEL_ORDER if model_artifacts_available(model_name)]


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
    if best in SUPPORTED_MODEL_NAMES:
        return best

    fallback_models = available_models_from_artifacts()
    if fallback_models:
        return fallback_models[0]

    raise FileNotFoundError(
        "Best model is not available and no complete local/S3 model artifacts were found. "
        "Train at least one model first or request model='lstm'/'rnn' after restoring artifacts."
    )
