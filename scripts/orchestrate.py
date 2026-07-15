from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import _bootstrap  # noqa: F401
from stock_forecast.artifacts import (
    BEST_MODEL_PATH,
    LSTM_BUNDLE_PATH,
    LSTM_MODEL_PATH,
    RNN_BUNDLE_PATH,
    RNN_MODEL_PATH,
    SUPPORTED_MODEL_NAMES,
)
from stock_forecast.config import DEFAULT_CSV_PATH, METRICS_PATH, REPORTS_DIR
from stock_forecast.data import load_price_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PYTHON_COMMAND = [PYTHON, "-B"]
COMPARISON_PATH = REPORTS_DIR / "recurrent_architecture_comparison.json"
ORCHESTRATION_PATH = REPORTS_DIR / "orchestration_summary.json"


@dataclass
class StepResult:
    name: str
    status: str
    command: list[str] | None = None
    detail: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orchestrate data collection, recurrent model training and validations."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--architectures",
        nargs="+",
        default=None,
        help="Optional architecture names passed to train_recurrent_models.py.",
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Download the dataset before training, even if the CSV already exists.",
    )
    parser.add_argument(
        "--skip-train",
        action="store_true",
        help="Only validate existing artifacts and run tests.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the pytest validation step.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Fast smoke run: 3 epochs, patience 1, simple RNN and simple LSTM only.",
    )
    return parser.parse_args()


def run_command(name: str, command: list[str]) -> StepResult:
    print(f"\n>>> {name}", flush=True)
    print(" ".join(command), flush=True)
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    if completed.returncode != 0:
        raise RuntimeError(f"Step failed: {name} (exit code {completed.returncode})")
    return StepResult(name=name, status="ok", command=command)


def read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_dataset(csv_path: Path) -> StepResult:
    df = load_price_csv(csv_path)
    detail = f"{len(df)} rows, {df['Date'].min().date()} to {df['Date'].max().date()}"
    if len(df) < 120:
        raise ValueError(f"Dataset is too small for recurrent training: {detail}")
    print(f"Dataset OK: {detail}")
    return StepResult(name="validate_dataset", status="ok", detail=detail)


def validate_model_artifacts() -> StepResult:
    required_paths = [
        RNN_MODEL_PATH,
        RNN_BUNDLE_PATH,
        LSTM_MODEL_PATH,
        LSTM_BUNDLE_PATH,
        METRICS_PATH,
        BEST_MODEL_PATH,
        COMPARISON_PATH,
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing expected artifacts: {missing}")

    metrics = read_json(METRICS_PATH)
    comparison = read_json(COMPARISON_PATH)
    best_payload = read_json(BEST_MODEL_PATH)
    best_model = best_payload.get("best_model")
    if best_model not in SUPPORTED_MODEL_NAMES:
        raise ValueError(f"Invalid best_model: {best_model}")

    for model_name in sorted(SUPPORTED_MODEL_NAMES):
        payload = metrics.get(model_name)
        if not payload:
            raise ValueError(f"Missing metrics for {model_name}.")
        for metric_name in ("mae", "rmse", "mape"):
            if metric_name not in payload["test_metrics"]:
                raise ValueError(f"Missing {model_name} test metric: {metric_name}")

    tested = comparison.get("architectures_tested", [])
    if not tested:
        raise ValueError("No architectures found in recurrent architecture comparison report.")

    detail = (
        f"best_model={best_model}, "
        f"rnn_rmse={metrics['rnn']['test_metrics']['rmse']:.4f}, "
        f"lstm_rmse={metrics['lstm']['test_metrics']['rmse']:.4f}, "
        f"architectures={len(tested)}"
    )
    print(f"Artifacts OK: {detail}")
    return StepResult(name="validate_artifacts", status="ok", detail=detail)


def write_summary(results: list[StepResult]) -> None:
    payload = {
        "status": "ok",
        "steps": [
            {
                "name": result.name,
                "status": result.status,
                "command": result.command,
                "detail": result.detail,
            }
            for result in results
        ],
    }
    ORCHESTRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    ORCHESTRATION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSummary saved to {ORCHESTRATION_PATH}")


def main() -> None:
    args = parse_args()
    try:
        if args.quick:
            args.epochs = 3
            args.patience = 1
            args.architectures = ["rnn_simple_30", "lstm_simple_30"]

        results: list[StepResult] = []
        if args.collect or not args.input.exists():
            results.append(
                run_command("collect_data", [*PYTHON_COMMAND, "scripts/collect_data.py"])
            )

        results.append(validate_dataset(args.input))

        if not args.skip_train:
            train_command = [
                *PYTHON_COMMAND,
                "scripts/train_recurrent_models.py",
                "--input",
                str(args.input),
                "--epochs",
                str(args.epochs),
                "--patience",
                str(args.patience),
                "--seed",
                str(args.seed),
            ]
            if args.architectures:
                train_command.extend(["--architectures", *args.architectures])
            results.append(run_command("train_recurrent_models", train_command))

        results.append(validate_model_artifacts())

        if not args.skip_tests:
            results.append(run_command("pytest", [*PYTHON_COMMAND, "-m", "pytest", "-q"]))

        write_summary(results)
    except Exception as exc:
        print(f"\nOrchestration failed: {exc}", file=sys.stderr)
        if args.skip_train:
            print(
                "Existing artifacts are incomplete. Run `python3 scripts/orchestrate.py --quick` "
                "for a smoke training run or `python3 scripts/orchestrate.py` for the full run.",
                file=sys.stderr,
            )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
