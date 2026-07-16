from pathlib import Path

from stock_forecast import inference


def test_resolve_saved_model_path_remaps_absolute_training_path(monkeypatch, tmp_path):
    models_dir = tmp_path / "models"
    monkeypatch.setattr(inference, "MODELS_DIR", models_dir)

    resolved = inference._resolve_saved_model_path(
        "/home/capizani/FIAP/Tech-Challenge-4/models/lstm.keras"
    )

    assert resolved == models_dir / "lstm.keras"


def test_resolve_saved_model_path_keeps_non_model_path():
    path = Path("/tmp/custom/lstm.keras")

    assert inference._resolve_saved_model_path(path) == path
