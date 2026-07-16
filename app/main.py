from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from stock_forecast.artifacts import (
    BEST_MODEL_PATH,
    METRICS_PATH,
    available_models_from_artifacts,
)
from stock_forecast.config import DEFAULT_SYMBOL
from stock_forecast.inference import predict_next_close_from_frame
from stock_forecast.metrics import read_json


class PriceCandle(BaseModel):
    date: dt.date = Field(..., description="Trading date.")
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: float = Field(..., ge=0)


class PredictionRequest(BaseModel):
    symbol: str = DEFAULT_SYMBOL
    history: list[PriceCandle] = Field(..., min_length=21)


class PredictionResponse(BaseModel):
    symbol: str
    model: str
    horizon: str
    prediction_next_close: float


app = FastAPI(
    title="PETR4.SA Stock Forecast API",
    version="1.0.0",
    description="Serves RNN and LSTM forecasts for the next trading close price.",
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "symbol": DEFAULT_SYMBOL,
        "best_model": read_json(BEST_MODEL_PATH, default={}).get("best_model"),
        "available_models": available_models_from_artifacts(),
        "metrics_available": METRICS_PATH.exists(),
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(
    payload: PredictionRequest,
    model: Literal["rnn", "lstm", "best"] = Query(default="best"),
) -> PredictionResponse:
    df = pd.DataFrame(
        [
            {
                "Date": candle.date,
                "Open": candle.open,
                "High": candle.high,
                "Low": candle.low,
                "Close": candle.close,
                "Volume": candle.volume,
            }
            for candle in payload.history
        ]
    )

    try:
        resolved_model, prediction = predict_next_close_from_frame(df, model)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PredictionResponse(
        symbol=payload.symbol,
        model=resolved_model,
        horizon="next_trading_day_close",
        prediction_next_close=round(prediction, 4),
    )
