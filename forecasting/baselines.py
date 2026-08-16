"""Simple forecasting baselines.

Baselines are intentionally first-class models in NovaPlan.  A more complex
model should only be selected when it improves on these transparent rules in
an out-of-sample backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


def _as_series(values: Any) -> np.ndarray:
    """Return finite values as a one-dimensional float array."""

    array = np.asarray(values, dtype=float).reshape(-1)
    if array.size == 0:
        raise ValueError("At least one historical observation is required.")
    if not np.isfinite(array).all():
        raise ValueError("Historical observations must be finite.")
    return array


def _prediction_horizon(X: Any = None, horizon: int | None = None) -> int:
    """Resolve a sklearn-style prediction input or an explicit horizon."""

    if horizon is not None:
        steps = int(horizon)
    elif isinstance(X, (int, np.integer)):
        steps = int(X)
    elif X is None:
        steps = 1
    else:
        steps = len(X)
    if steps < 1:
        raise ValueError("Forecast horizon must be at least one.")
    return steps


def seasonal_naive(
    history: Any,
    horizon: int,
    season_length: int = 12,
) -> np.ndarray:
    """Repeat the most recent complete (or partial) seasonal pattern.

    For monthly business data, ``season_length=12`` predicts each month from
    the same month in the previous year.  With less than one full season, the
    latest available observation is used as a conservative fallback.
    """

    values = _as_series(history)
    if season_length < 1:
        raise ValueError("season_length must be at least one.")
    if horizon < 1:
        raise ValueError("horizon must be at least one.")
    pattern = values[-season_length:] if values.size >= season_length else values[-1:]
    return np.resize(pattern, horizon).astype(float, copy=False)


@dataclass
class SeasonalNaiveForecaster:
    """Scikit-learn-like wrapper around :func:`seasonal_naive`."""

    season_length: int = 12
    _history: np.ndarray = field(init=False, repr=False)
    requires_features: bool = field(default=False, init=False)

    def fit(self, X: Any, y: Any | None = None) -> "SeasonalNaiveForecaster":
        """Store target history; features are accepted and ignored."""

        self._history = _as_series(X if y is None else y)
        return self

    def predict(self, X: Any = None, horizon: int | None = None) -> np.ndarray:
        """Forecast the requested number of periods."""

        if not hasattr(self, "_history"):
            raise RuntimeError("Call fit before predict.")
        steps = _prediction_horizon(X, horizon)
        return seasonal_naive(self._history, steps, self.season_length)


@dataclass
class NaiveForecaster:
    """Repeat the latest observation."""

    _last_value: float = field(init=False, repr=False)
    requires_features: bool = field(default=False, init=False)

    def fit(self, X: Any, y: Any | None = None) -> "NaiveForecaster":
        values = _as_series(X if y is None else y)
        self._last_value = float(values[-1])
        return self

    def predict(self, X: Any = None, horizon: int | None = None) -> np.ndarray:
        if not hasattr(self, "_last_value"):
            raise RuntimeError("Call fit before predict.")
        return np.full(_prediction_horizon(X, horizon), self._last_value)


@dataclass
class RollingMeanForecaster:
    """Repeat the mean of the latest ``window`` observations."""

    window: int = 3
    _mean: float = field(init=False, repr=False)
    requires_features: bool = field(default=False, init=False)

    def fit(self, X: Any, y: Any | None = None) -> "RollingMeanForecaster":
        if self.window < 1:
            raise ValueError("window must be at least one.")
        values = _as_series(X if y is None else y)
        self._mean = float(np.mean(values[-self.window :]))
        return self

    def predict(self, X: Any = None, horizon: int | None = None) -> np.ndarray:
        if not hasattr(self, "_mean"):
            raise RuntimeError("Call fit before predict.")
        return np.full(_prediction_horizon(X, horizon), self._mean)
