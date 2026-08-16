"""Time-series-safe backtesting and forecast comparison utilities."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from forecasting.baselines import SeasonalNaiveForecaster
from forecasting.machine_learning import HistGradientBoostingForecaster
from forecasting.statistical import DriverRegressionForecaster, ElasticNetForecaster


def _aligned_arrays(y_true: Any, y_pred: Any) -> tuple[np.ndarray, np.ndarray]:
    actual = np.asarray(y_true, dtype=float).reshape(-1)
    predicted = np.asarray(y_pred, dtype=float).reshape(-1)
    if actual.size == 0 or actual.size != predicted.size:
        raise ValueError("Actual and predicted values must have equal, non-zero length.")
    mask = np.isfinite(actual) & np.isfinite(predicted)
    if not mask.any():
        raise ValueError("No finite actual/predicted pairs were supplied.")
    return actual[mask], predicted[mask]


def mae(y_true: Any, y_pred: Any) -> float:
    """Mean absolute error."""

    actual, predicted = _aligned_arrays(y_true, y_pred)
    return float(np.mean(np.abs(actual - predicted)))


def rmse(y_true: Any, y_pred: Any) -> float:
    """Root mean squared error."""

    actual, predicted = _aligned_arrays(y_true, y_pred)
    return float(np.sqrt(np.mean(np.square(actual - predicted))))


def wape(y_true: Any, y_pred: Any) -> float:
    """Weighted absolute percentage error as a fraction, not a percentage."""

    actual, predicted = _aligned_arrays(y_true, y_pred)
    denominator = float(np.sum(np.abs(actual)))
    return float(np.sum(np.abs(actual - predicted)) / denominator) if denominator else np.nan


def directional_accuracy(
    y_true: Any,
    y_pred: Any,
    previous_actual: float | None = None,
) -> float:
    """Share of periods for which the predicted direction is correct.

    ``previous_actual`` enables the metric for a single-period forecast.  If it
    is omitted, consecutive observations within the supplied arrays are used.
    Flat-to-flat is counted as correct.
    """

    actual, predicted = _aligned_arrays(y_true, y_pred)
    if previous_actual is None:
        if actual.size < 2:
            return np.nan
        actual_change = np.diff(actual)
        predicted_change = np.diff(predicted)
    else:
        actual_change = np.diff(np.r_[float(previous_actual), actual])
        predicted_change = np.diff(np.r_[float(previous_actual), predicted])
    return float(np.mean(np.sign(actual_change) == np.sign(predicted_change)))


def forecast_metrics(y_true: Any, y_pred: Any) -> dict[str, float]:
    """Return the standard NovaPlan error metrics."""

    return {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "wape": wape(y_true, y_pred),
        "directional_accuracy": directional_accuracy(y_true, y_pred),
    }


calculate_metrics = forecast_metrics


@dataclass(frozen=True)
class WalkForwardResult:
    """Predictions and summary metrics from one expanding-window backtest."""

    predictions: pd.DataFrame
    metrics: dict[str, float]


def _validate_backtest_sizes(
    observations: int,
    initial_train_size: int,
    horizon: int,
    step: int,
) -> None:
    if initial_train_size < 2:
        raise ValueError("initial_train_size must be at least two.")
    if horizon < 1 or step < 1:
        raise ValueError("horizon and step must be at least one.")
    if initial_train_size + horizon > observations:
        raise ValueError("Not enough observations for the requested backtest.")


def walk_forward_backtest(
    model: Any,
    X: pd.DataFrame | np.ndarray,
    y: Sequence[float] | pd.Series,
    *,
    initial_train_size: int,
    horizon: int = 1,
    step: int = 1,
    dates: Sequence[Any] | None = None,
) -> WalkForwardResult:
    """Evaluate ``model`` with an expanding training window.

    Each fold trains strictly on rows before its forecast origin.  No random
    splitting or shuffling is performed.  Multi-step folds are supported; set
    ``step=horizon`` for non-overlapping test windows.
    """

    features = X.copy() if isinstance(X, pd.DataFrame) else np.asarray(X)
    target = np.asarray(y, dtype=float).reshape(-1)
    if len(features) != target.size:
        raise ValueError("X and y must contain the same number of rows.")
    _validate_backtest_sizes(target.size, initial_train_size, horizon, step)
    date_values = np.asarray(dates if dates is not None else np.arange(target.size))
    if date_values.size != target.size:
        raise ValueError("dates must have the same length as y.")

    rows: list[dict[str, Any]] = []
    for origin in range(initial_train_size, target.size - horizon + 1, step):
        fitted = deepcopy(model)
        fitted.fit(features[:origin], target[:origin])
        fold_prediction = np.asarray(
            fitted.predict(features[origin : origin + horizon]),
            dtype=float,
        ).reshape(-1)
        if fold_prediction.size != horizon:
            raise ValueError("Model returned a different number of predictions than requested.")
        for offset, prediction in enumerate(fold_prediction):
            position = origin + offset
            rows.append(
                {
                    "origin_position": origin,
                    "position": position,
                    "date": date_values[position],
                    "horizon": offset + 1,
                    "actual": target[position],
                    "predicted": prediction,
                    "previous_actual": target[position - 1],
                }
            )

    predictions = pd.DataFrame(rows)
    metrics = forecast_metrics(predictions["actual"], predictions["predicted"])
    directions = np.sign(predictions["actual"] - predictions["previous_actual"])
    predicted_directions = np.sign(
        predictions["predicted"] - predictions["previous_actual"]
    )
    metrics["directional_accuracy"] = float(np.mean(directions == predicted_directions))
    return WalkForwardResult(predictions=predictions, metrics=metrics)


walk_forward_evaluate = walk_forward_backtest


def default_models(season_length: int = 12) -> dict[str, Any]:
    """Return the four benchmark models requested by the MVP methodology."""

    return {
        "Seasonal Naive": SeasonalNaiveForecaster(season_length=season_length),
        "Driver Regression": DriverRegressionForecaster(),
        "ElasticNet": ElasticNetForecaster(),
        "HistGradientBoosting": HistGradientBoostingForecaster(),
    }


def compare_models(
    data: pd.DataFrame,
    *,
    target_column: str,
    feature_columns: Sequence[str],
    models: Mapping[str, Any] | None = None,
    date_column: str | None = "month",
    initial_train_size: int = 36,
    horizon: int = 1,
    step: int = 1,
    season_length: int = 12,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backtest models and return a comparison table plus fold predictions.

    The returned table is sorted by WAPE (lower is better).  WAPE remains a
    fraction internally, making chart formatting explicit and less error-prone.
    """

    required = {target_column, *feature_columns}
    if date_column is not None:
        required.add(date_column)
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Missing backtest columns: {missing}")
    ordered = data.sort_values(date_column).reset_index(drop=True) if date_column else data.reset_index(drop=True)
    dates = ordered[date_column] if date_column else None
    features = ordered[list(feature_columns)]
    target = ordered[target_column]
    candidates = dict(models) if models is not None else default_models(season_length)
    if not candidates:
        raise ValueError("At least one model is required.")

    summaries: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    for model_name, model in candidates.items():
        result = walk_forward_backtest(
            model,
            features,
            target,
            initial_train_size=initial_train_size,
            horizon=horizon,
            step=step,
            dates=dates,
        )
        summaries.append(
            {
                "Model": model_name,
                "MAE": result.metrics["mae"],
                "RMSE": result.metrics["rmse"],
                "WAPE": result.metrics["wape"],
                "Directional Accuracy": result.metrics["directional_accuracy"],
                "Predictions": len(result.predictions),
            }
        )
        model_predictions = result.predictions.copy()
        model_predictions.insert(0, "Model", model_name)
        prediction_frames.append(model_predictions)

    comparison = pd.DataFrame(summaries).sort_values(["WAPE", "MAE"]).reset_index(drop=True)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    return comparison, predictions


def model_comparison_table(*args: Any, **kwargs: Any) -> pd.DataFrame:
    """Convenience API returning only the presentation-ready metric table."""

    table, _ = compare_models(*args, **kwargs)
    return table


def complexity_insight(
    comparison: pd.DataFrame,
    *,
    driver_model: str = "Driver Regression",
    complex_model: str = "HistGradientBoosting",
) -> str:
    """Explain whether nonlinear complexity materially improves WAPE."""

    indexed = comparison.set_index("Model")
    if driver_model not in indexed.index or complex_model not in indexed.index:
        return "Complexity comparison is unavailable for the selected models."
    driver_wape = float(indexed.loc[driver_model, "WAPE"])
    complex_wape = float(indexed.loc[complex_model, "WAPE"])
    improvement_pp = (driver_wape - complex_wape) * 100
    if improvement_pp <= 0:
        return (
            f"{complex_model} does not improve WAPE versus the interpretable "
            f"{driver_model}; retain the driver model unless another business need justifies it."
        )
    qualifier = "only " if improvement_pp < 1.0 else ""
    return (
        f"{complex_model} improves WAPE by {qualifier}{improvement_pp:.1f} percentage "
        f"points versus the interpretable {driver_model}."
    )
