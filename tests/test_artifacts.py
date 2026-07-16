from stock_forecast import artifacts
from stock_forecast.metrics import write_json


def test_should_replace_model_when_metric_improves(tmp_path, monkeypatch):
    metrics_path = tmp_path / "metrics.json"
    model_path = tmp_path / "lstm.keras"
    bundle_path = tmp_path / "lstm_bundle.joblib"
    model_path.write_text("model", encoding="utf-8")
    bundle_path.write_text("bundle", encoding="utf-8")
    write_json(metrics_path, {"lstm": {"test_metrics": {"rmse": 1.0}}})

    monkeypatch.setattr(artifacts, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(artifacts, "MODEL_ARTIFACT_PATHS", {"lstm": (model_path, bundle_path)})

    should_save, reason = artifacts.should_replace_model(
        "lstm", {"test_metrics": {"rmse": 0.9}}
    )

    assert should_save is True
    assert "improved" in reason


def test_should_not_replace_model_when_metric_does_not_improve(tmp_path, monkeypatch):
    metrics_path = tmp_path / "metrics.json"
    model_path = tmp_path / "lstm.keras"
    bundle_path = tmp_path / "lstm_bundle.joblib"
    model_path.write_text("model", encoding="utf-8")
    bundle_path.write_text("bundle", encoding="utf-8")
    write_json(metrics_path, {"lstm": {"test_metrics": {"rmse": 1.0}}})

    monkeypatch.setattr(artifacts, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(artifacts, "MODEL_ARTIFACT_PATHS", {"lstm": (model_path, bundle_path)})

    should_save, reason = artifacts.should_replace_model(
        "lstm", {"test_metrics": {"rmse": 1.1}}
    )

    assert should_save is False
    assert "did not improve" in reason


def test_should_replace_model_when_artifact_is_missing(tmp_path, monkeypatch):
    metrics_path = tmp_path / "metrics.json"
    model_path = tmp_path / "lstm.keras"
    bundle_path = tmp_path / "lstm_bundle.joblib"
    model_path.write_text("model", encoding="utf-8")
    write_json(metrics_path, {"lstm": {"test_metrics": {"rmse": 1.0}}})

    monkeypatch.setattr(artifacts, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(artifacts, "MODEL_ARTIFACT_PATHS", {"lstm": (model_path, bundle_path)})

    should_save, reason = artifacts.should_replace_model(
        "lstm", {"test_metrics": {"rmse": 1.1}}
    )

    assert should_save is True
    assert "missing artifacts" in reason


def test_resolve_best_falls_back_to_lstm_when_reports_are_missing(tmp_path, monkeypatch):
    lstm_model = tmp_path / "lstm.keras"
    lstm_bundle = tmp_path / "lstm_bundle.joblib"
    rnn_model = tmp_path / "rnn.keras"
    rnn_bundle = tmp_path / "rnn_bundle.joblib"
    for path in (lstm_model, lstm_bundle, rnn_model, rnn_bundle):
        path.write_text("artifact", encoding="utf-8")

    monkeypatch.setattr(artifacts, "BEST_MODEL_PATH", tmp_path / "best_model.json")
    monkeypatch.setattr(
        artifacts,
        "MODEL_ARTIFACT_PATHS",
        {
            "lstm": (lstm_model, lstm_bundle),
            "rnn": (rnn_model, rnn_bundle),
        },
    )

    assert artifacts.resolve_model_name("best") == "lstm"


def test_resolve_best_raises_when_reports_and_artifacts_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "BEST_MODEL_PATH", tmp_path / "best_model.json")
    monkeypatch.setattr(
        artifacts,
        "MODEL_ARTIFACT_PATHS",
        {
            "lstm": (tmp_path / "lstm.keras", tmp_path / "lstm_bundle.joblib"),
            "rnn": (tmp_path / "rnn.keras", tmp_path / "rnn_bundle.joblib"),
        },
    )

    try:
        artifacts.resolve_model_name("best")
    except FileNotFoundError as exc:
        assert "no complete local/S3 model artifacts" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")
