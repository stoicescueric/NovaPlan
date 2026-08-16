"""Interpretable driver and regularised statistical forecasters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def _to_frame(X: Any, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """Coerce features to a numeric frame while retaining useful labels."""

    if isinstance(X, pd.DataFrame):
        frame = X.copy()
    else:
        array = np.asarray(X)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        frame = pd.DataFrame(array, columns=columns)
    if frame.empty:
        raise ValueError("At least one feature row is required.")
    try:
        return frame.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Forecast features must be numeric.") from exc


def _to_target(y: Any) -> np.ndarray:
    target = np.asarray(y, dtype=float).reshape(-1)
    if target.size == 0 or not np.isfinite(target).all():
        raise ValueError("Target observations must be finite and non-empty.")
    return target


@dataclass
class DriverRegressionForecaster:
    """Transparent multivariate linear model of planned business drivers.

    The caller chooses operational features (for example headcount,
    utilisation and billing rate).  Keeping that selection explicit avoids
    accidentally training on downstream accounting outcomes.
    """

    fit_intercept: bool = True
    model_: Pipeline = field(init=False, repr=False)
    feature_names_: list[str] = field(init=False)
    requires_features: bool = field(default=True, init=False)

    def fit(self, X: Any, y: Any) -> "DriverRegressionForecaster":
        frame = _to_frame(X)
        target = _to_target(y)
        if len(frame) != target.size:
            raise ValueError("X and y must contain the same number of rows.")
        self.feature_names_ = [str(column) for column in frame.columns]
        self.model_ = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("regression", LinearRegression(fit_intercept=self.fit_intercept)),
            ]
        )
        self.model_.fit(frame, target)
        return self

    def predict(self, X: Any) -> np.ndarray:
        if not hasattr(self, "model_"):
            raise RuntimeError("Call fit before predict.")
        frame = _to_frame(X, self.feature_names_)
        if isinstance(X, pd.DataFrame):
            missing = [name for name in self.feature_names_ if name not in frame.columns]
            if missing:
                raise ValueError(f"Missing forecast features: {missing}")
            frame = frame[self.feature_names_]
        return np.asarray(self.model_.predict(frame), dtype=float)

    @property
    def coefficients_(self) -> pd.Series:
        """Return coefficients indexed by driver name."""

        if not hasattr(self, "model_"):
            raise RuntimeError("Call fit before reading coefficients.")
        regression = self.model_.named_steps["regression"]
        return pd.Series(regression.coef_, index=self.feature_names_, name="coefficient")


# A concise alias used by the diagnostics layer.
DriverBasedForecaster = DriverRegressionForecaster


@dataclass
class ElasticNetForecaster:
    """Regularised linear benchmark suitable for correlated business drivers."""

    alpha: float = 0.01
    l1_ratio: float = 0.25
    max_iter: int = 20_000
    model_: Pipeline = field(init=False, repr=False)
    feature_names_: list[str] = field(init=False)
    requires_features: bool = field(default=True, init=False)

    def fit(self, X: Any, y: Any) -> "ElasticNetForecaster":
        if self.alpha < 0:
            raise ValueError("alpha cannot be negative.")
        if not 0 <= self.l1_ratio <= 1:
            raise ValueError("l1_ratio must be between zero and one.")
        frame = _to_frame(X)
        target = _to_target(y)
        if len(frame) != target.size:
            raise ValueError("X and y must contain the same number of rows.")
        self.feature_names_ = [str(column) for column in frame.columns]
        self.model_ = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                (
                    "elastic_net",
                    ElasticNet(
                        alpha=self.alpha,
                        l1_ratio=self.l1_ratio,
                        max_iter=self.max_iter,
                        selection="cyclic",
                    ),
                ),
            ]
        )
        self.model_.fit(frame, target)
        return self

    def predict(self, X: Any) -> np.ndarray:
        if not hasattr(self, "model_"):
            raise RuntimeError("Call fit before predict.")
        frame = _to_frame(X, self.feature_names_)
        if isinstance(X, pd.DataFrame):
            missing = [name for name in self.feature_names_ if name not in frame.columns]
            if missing:
                raise ValueError(f"Missing forecast features: {missing}")
            frame = frame[self.feature_names_]
        return np.asarray(self.model_.predict(frame), dtype=float)


def revenue_from_drivers(
    drivers: pd.DataFrame,
    hours_per_day: float = 8.0,
) -> pd.Series:
    """Calculate an auditable services-revenue baseline from operating drivers.

    Expected columns are ``headcount``, ``billable_share``, ``working_days``,
    ``utilization``, ``billing_rate_eur`` and ``realization_rate``.  Optional
    ``contractor_revenue_eur`` and ``backlog_conversion_eur`` are added when
    present.
    """

    required = {
        "headcount",
        "billable_share",
        "working_days",
        "utilization",
        "billing_rate_eur",
        "realization_rate",
    }
    missing = sorted(required.difference(drivers.columns))
    if missing:
        raise ValueError(f"Missing revenue drivers: {missing}")
    if hours_per_day <= 0:
        raise ValueError("hours_per_day must be positive.")

    revenue = (
        drivers["headcount"]
        * drivers["billable_share"]
        * drivers["working_days"]
        * hours_per_day
        * drivers["utilization"]
        * drivers["billing_rate_eur"]
        * drivers["realization_rate"]
    )
    for optional_component in ("contractor_revenue_eur", "backlog_conversion_eur"):
        if optional_component in drivers:
            revenue = revenue + drivers[optional_component]
    return pd.Series(revenue, index=drivers.index, name="revenue_eur", dtype=float)
