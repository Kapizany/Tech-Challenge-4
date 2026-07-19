from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request, Response
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from stock_forecast.artifacts import (
    BEST_MODEL_PATH,
    METRICS_PATH,
    MODEL_ARTIFACT_PATHS,
    available_models_from_artifacts,
)
from stock_forecast.collection import collect_price_history
from stock_forecast.config import DEFAULT_SYMBOL, PROJECT_ROOT, RAW_DATA_DIR
from stock_forecast.data import load_price_csv, normalize_symbol, symbol_price_csv_path
from stock_forecast.inference import predict_next_close_from_frame
from stock_forecast.metrics import read_json
from stock_forecast.storage import (
    configured_data_s3_location,
    configured_models_s3_location,
    delete_s3_key_versions,
    delete_s3_prefix_versions,
    list_s3_keys,
    s3_key_for_path,
)

LOGGER = logging.getLogger("stock_forecast.api")
LOGGER.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
TRACE_REQUESTS = os.getenv("TRACE_REQUESTS", "true").lower() == "true"
TRACE_LOG_BODIES = os.getenv("TRACE_LOG_BODIES", "true").lower() == "true"
TRACE_MAX_BODY_CHARS = int(os.getenv("TRACE_MAX_BODY_CHARS", "4000"))
TRACE_EXCLUDED_PATHS = {
    path.strip()
    for path in os.getenv("TRACE_EXCLUDED_PATHS", "/health,/metrics").split(",")
    if path.strip()
}


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


class CollectRequest(BaseModel):
    symbol: str = DEFAULT_SYMBOL
    start: dt.date
    end: dt.date
    upload_s3: bool = True


class CollectResponse(BaseModel):
    symbol: str
    start: dt.date
    end: dt.date
    rows: int
    local_path: str
    uploaded_to_s3: bool
    s3_object_already_exists: bool = False
    s3_bucket: str | None = None
    s3_key: str | None = None


class ModelArtifactInfo(BaseModel):
    name: str
    available: bool
    local_paths: list[str]
    s3_keys: list[str]


class ModelsResponse(BaseModel):
    symbol: str | None = None
    available_models: list[str]
    artifacts: list[ModelArtifactInfo]


class DataFileInfo(BaseModel):
    symbol: str
    source: Literal["local", "s3"]
    path: str | None = None
    s3_bucket: str | None = None
    s3_key: str | None = None
    rows: int | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class DataByTickerResponse(BaseModel):
    symbol: str
    files: list[DataFileInfo]


class DataCleanupResponse(BaseModel):
    symbol: str
    deleted_local_paths: list[str]
    deleted_s3_bucket: str | None = None
    deleted_s3_prefixes: list[str]
    deleted_s3_objects: int


class TickerListResponse(BaseModel):
    tickers: list[str]


app = FastAPI(
    title="PETR4.SA Stock Forecast API",
    version="1.0.0",
    description="Serves RNN and LSTM forecasts for the next trading close price.",
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _local_data_files_by_symbol() -> dict[str, list[Path]]:
    files_by_symbol: dict[str, list[Path]] = {}
    if not RAW_DATA_DIR.exists():
        return files_by_symbol

    for path in RAW_DATA_DIR.rglob("*.csv"):
        if path.parent == RAW_DATA_DIR:
            symbol = path.stem.upper()
        else:
            symbol = path.parent.name.upper()
        files_by_symbol.setdefault(symbol, []).append(path)
    return files_by_symbol


def _s3_data_keys_by_symbol() -> tuple[str | None, dict[str, list[str]]]:
    bucket, prefix = configured_data_s3_location()
    if not bucket:
        return None, {}

    normalized_prefix = prefix.strip("/")
    keys = list_s3_keys(bucket, normalized_prefix)
    keys_by_symbol: dict[str, list[str]] = {}
    for key in keys:
        parts = key.split("/")
        if not key.endswith(".csv"):
            continue
        if "raw" in parts and parts.index("raw") + 1 < len(parts):
            raw_index = parts.index("raw")
            if raw_index + 2 < len(parts):
                symbol = parts[raw_index + 1].upper()
            else:
                symbol = Path(parts[-1]).stem.upper()
            keys_by_symbol.setdefault(symbol, []).append(key)
    return bucket, keys_by_symbol


def _data_file_info_from_local(symbol: str, path: Path) -> DataFileInfo:
    try:
        df = load_price_csv(path)
        rows = len(df)
        start_date = df["Date"].min().date() if rows else None
        end_date = df["Date"].max().date() if rows else None
    except Exception:
        rows = None
        start_date = None
        end_date = None
    return DataFileInfo(
        symbol=symbol,
        source="local",
        path=_relative_path(path),
        rows=rows,
        start_date=start_date,
        end_date=end_date,
    )


def _data_s3_key(prefix: str, suffix: str) -> str:
    normalized_prefix = prefix.strip("/")
    suffix = suffix.strip("/")
    if normalized_prefix:
        return f"{normalized_prefix}/{suffix}"
    return suffix


def _data_s3_prefixes_for_symbol(symbol: str) -> list[str]:
    _, prefix = configured_data_s3_location()
    normalized_symbol = normalize_symbol(symbol)
    return [
        _data_s3_key(prefix, f"data/raw/{normalized_symbol}/"),
        _data_s3_key(prefix, f"data/processed/{normalized_symbol}/"),
    ]


def _legacy_data_s3_keys_for_symbol(symbol: str) -> list[str]:
    _, prefix = configured_data_s3_location()
    normalized_symbol = normalize_symbol(symbol)
    return [
        _data_s3_key(prefix, f"data/raw/{normalized_symbol}.csv"),
        _data_s3_key(prefix, f"data/processed/{normalized_symbol}.csv"),
    ]


def _model_s3_keys_for_path(path: Path, symbol: str | None) -> list[str]:
    _, prefix = configured_models_s3_location()
    keys = [s3_key_for_path(path, prefix)]
    if symbol:
        normalized_prefix = prefix.strip("/")
        grouped_key = f"{symbol.upper()}/{path.name}"
        if normalized_prefix:
            grouped_key = f"{normalized_prefix}/{symbol.upper()}/models/{path.name}"
        else:
            grouped_key = f"{symbol.upper()}/models/{path.name}"
        keys.append(grouped_key)
    return list(dict.fromkeys(keys))


def _decode_body(body: bytes) -> object:
    if not body:
        return None

    text = body.decode("utf-8", errors="replace")
    if len(text) > TRACE_MAX_BODY_CHARS:
        return {
            "truncated": True,
            "size_bytes": len(body),
            "preview": text[:TRACE_MAX_BODY_CHARS],
        }

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def _request_with_cached_body(request: Request, body: bytes) -> Request:
    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive=receive)


@app.middleware("http")
async def trace_http_requests(request: Request, call_next) -> Response:
    if not TRACE_REQUESTS or request.url.path in TRACE_EXCLUDED_PATHS:
        return await call_next(request)

    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    started_at = time.perf_counter()
    request_body = await request.body()
    traced_request = await _request_with_cached_body(request, request_body)
    response_body = b""
    status_code = 500

    try:
        response = await call_next(traced_request)
        status_code = response.status_code
        async for chunk in response.body_iterator:
            response_body += chunk
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        LOGGER.exception(
            json.dumps(
                {
                    "event": "http_request_error",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": dict(request.query_params),
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
                ensure_ascii=True,
            )
        )
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    log_payload = {
        "event": "http_request",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "status_code": status_code,
        "duration_ms": duration_ms,
        "client": request.client.host if request.client else None,
    }
    if TRACE_LOG_BODIES:
        log_payload["request_body"] = _decode_body(request_body)
        log_payload["response_body"] = _decode_body(response_body)

    LOGGER.info(json.dumps(log_payload, ensure_ascii=True))
    headers = dict(response.headers)
    headers["x-request-id"] = request_id
    headers["x-process-time-ms"] = str(duration_ms)
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
        background=response.background,
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "symbol": DEFAULT_SYMBOL,
        "best_model": read_json(BEST_MODEL_PATH, default={}).get("best_model"),
        "available_models": available_models_from_artifacts(),
        "metrics_available": METRICS_PATH.exists(),
    }


@app.post("/collect", response_model=CollectResponse)
def collect(payload: CollectRequest) -> CollectResponse:
    if payload.end <= payload.start:
        raise HTTPException(status_code=400, detail="end must be after start.")

    try:
        result = collect_price_history(
            symbol=payload.symbol,
            start=payload.start.isoformat(),
            end=payload.end.isoformat(),
            output=symbol_price_csv_path(payload.symbol),
            upload_s3=payload.upload_s3,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CollectResponse(
        symbol=result.symbol,
        start=payload.start,
        end=payload.end,
        rows=result.rows,
        local_path=_relative_path(result.local_path),
        uploaded_to_s3=result.s3_uploaded,
        s3_object_already_exists=result.s3_object_already_exists,
        s3_bucket=result.s3_bucket,
        s3_key=result.s3_key,
    )


@app.get("/models", response_model=ModelsResponse)
def list_models(symbol: str | None = Query(default=None)) -> ModelsResponse:
    normalized_symbol = normalize_symbol(symbol) if symbol else None
    available = available_models_from_artifacts()
    artifacts = []

    for name, paths in MODEL_ARTIFACT_PATHS.items():
        local_paths = [_relative_path(path) for path in paths]
        s3_keys = []
        for path in paths:
            s3_keys.extend(_model_s3_keys_for_path(path, normalized_symbol))
        artifacts.append(
            ModelArtifactInfo(
                name=name,
                available=name in available,
                local_paths=local_paths,
                s3_keys=list(dict.fromkeys(s3_keys)),
            )
        )

    return ModelsResponse(
        symbol=normalized_symbol,
        available_models=available,
        artifacts=artifacts,
    )


@app.get("/data/tickers", response_model=TickerListResponse)
def list_data_tickers() -> TickerListResponse:
    local_symbols = set(_local_data_files_by_symbol())
    _, s3_symbols = _s3_data_keys_by_symbol()
    return TickerListResponse(tickers=sorted(local_symbols | set(s3_symbols)))


@app.get("/data/{symbol}", response_model=DataByTickerResponse)
def list_data_by_ticker(symbol: str) -> DataByTickerResponse:
    normalized_symbol = normalize_symbol(symbol)
    files: list[DataFileInfo] = []

    for path in _local_data_files_by_symbol().get(normalized_symbol, []):
        files.append(_data_file_info_from_local(normalized_symbol, path))

    bucket, s3_keys_by_symbol = _s3_data_keys_by_symbol()
    if bucket:
        for key in s3_keys_by_symbol.get(normalized_symbol, []):
            files.append(
                DataFileInfo(
                    symbol=normalized_symbol,
                    source="s3",
                    s3_bucket=bucket,
                    s3_key=key,
                )
            )

    return DataByTickerResponse(symbol=normalized_symbol, files=files)


@app.delete("/data/{symbol}", response_model=DataCleanupResponse)
def cleanup_data_by_ticker(symbol: str) -> DataCleanupResponse:
    normalized_symbol = normalize_symbol(symbol)
    deleted_local_paths: list[str] = []

    local_paths = [
        RAW_DATA_DIR / normalized_symbol,
        RAW_DATA_DIR / f"{normalized_symbol}.csv",
        PROJECT_ROOT / "data" / "processed" / normalized_symbol,
        PROJECT_ROOT / "data" / "processed" / f"{normalized_symbol}.csv",
    ]
    for path in local_paths:
        if path.is_dir():
            shutil.rmtree(path)
            deleted_local_paths.append(_relative_path(path))
        elif path.exists():
            path.unlink()
            deleted_local_paths.append(_relative_path(path))

    bucket, _ = configured_data_s3_location()
    deleted_s3_objects = 0
    deleted_s3_prefixes: list[str] = []
    if bucket:
        for prefix in _data_s3_prefixes_for_symbol(normalized_symbol):
            deleted = delete_s3_prefix_versions(bucket=bucket, prefix=prefix)
            deleted_s3_objects += deleted
            deleted_s3_prefixes.append(prefix)

        for key in _legacy_data_s3_keys_for_symbol(normalized_symbol):
            deleted = delete_s3_key_versions(bucket=bucket, key=key)
            deleted_s3_objects += deleted
            deleted_s3_prefixes.append(key)

    return DataCleanupResponse(
        symbol=normalized_symbol,
        deleted_local_paths=deleted_local_paths,
        deleted_s3_bucket=bucket,
        deleted_s3_prefixes=deleted_s3_prefixes,
        deleted_s3_objects=deleted_s3_objects,
    )


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
