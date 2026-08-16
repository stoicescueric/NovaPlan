"""Tests for transparent benchmarks and time-series-safe validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forecasting import (
    SeasonalNaiveForecaster,
    compare_models,
    directional_accuracy,
    forecast_metrics,
    revenue_from_drivers,
    walk_forward_backtest,
)


def test_forecast_metrics_have_clear_units() -> None:
    actual = np.array([100.0, 120.0, 110.0])
    predicted = np.array([90.0, 130.0, 100.0])

    metrics = forecast_metrics(actual, predicted)

    assert metrics["mae"] == pytest.approx(10.0)
    assert metrics["rmse"] == pytest.approx(10.0)
    assert metrics["wape"] == pytest.approx(30.0 / 330.0)
    assert metrics["directional_accuracy"] == pytest.approx(1.0)
    assert np.isnan(directional_accuracy([100.0], [101.0]))


def test_walk_forward_seasonal_baseline_uses_only_prior_history() -> None:
    target = np.arange(1.0, 17.0)
    features = pd.DataFrame({"known_driver": target * 100})

    result = walk_forward_backtest(
        SeasonalNaiveForecaster(season_length=4),
        features,
        target,
        initial_train_size=8,
        horizon=1,
    )

    # For every fold, the baseline must use t-4—not the current target or a
    # randomly selected future row.
    expected = target[result.predictions["position"].to_numpy() - 4]
    np.testing.assert_allclose(result.predictions["predicted"], expected)
    assert (result.predictions["origin_position"] <= result.predictions["position"]).all()


def test_driver_revenue_formula_responds_to_utilization_and_rate() -> None:
    drivers = pd.DataFrame(
        {
            "headcount": [280, 280, 280],
            "billable_share": [0.82, 0.82, 0.82],
            "working_days": [20, 20, 20],
            "utilization": [0.70, 0.78, 0.70],
            "billing_rate_eur": [60, 60, 66],
            "realization_rate": [0.97, 0.97, 0.97],
        }
    )

    revenue = revenue_from_drivers(drivers)

    assert revenue.iloc[1] > revenue.iloc[0]
    assert revenue.iloc[2] > revenue.iloc[0]
    assert revenue.iloc[1] / revenue.iloc[0] == pytest.approx(0.78 / 0.70)
    assert revenue.iloc[2] / revenue.iloc[0] == pytest.approx(1.10)


def test_model_comparison_api_returns_all_benchmarks() -> None:
    periods = 42
    positions = np.arange(periods)
    frame = pd.DataFrame(
        {
            "month": pd.date_range("2022-01-01", periods=periods, freq="MS"),
            "headcount": 250 + positions,
            "utilization": 0.74 + 0.04 * np.sin(positions * 2 * np.pi / 12),
            "billing_rate_eur": 55 + positions * 0.15,
        }
    )
    frame["revenue_eur"] = (
        frame["headcount"]
        * frame["utilization"]
        * frame["billing_rate_eur"]
        * 160
    )

    table, predictions = compare_models(
        frame,
        target_column="revenue_eur",
        feature_columns=["headcount", "utilization", "billing_rate_eur"],
        initial_train_size=30,
    )

    assert set(table["Model"]) == {
        "Seasonal Naive",
        "Driver Regression",
        "ElasticNet",
        "HistGradientBoosting",
    }
    assert {"MAE", "RMSE", "WAPE", "Directional Accuracy"}.issubset(table.columns)
    assert table["WAPE"].is_monotonic_increasing
    assert len(predictions) == 4 * (periods - 30)
