import numpy as np

from stock_forecast.metrics import regression_metrics


def test_regression_metrics_returns_expected_keys():
    metrics = regression_metrics(np.array([10.0, 20.0]), np.array([12.0, 18.0]))

    assert set(metrics) == {"mae", "rmse", "mape"}
    assert metrics["mae"] == 2.0
    assert round(metrics["rmse"], 4) == 2.0
    assert round(metrics["mape"], 4) == 15.0
