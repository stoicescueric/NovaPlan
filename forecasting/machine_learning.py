"""Compact nonlinear benchmark for NovaPlan forecasting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from forecasting.statistical import _to_frame, _to_target


@dataclass
class HistGradientBoostingForecaster:
    """A bounded-complexity tree model using only scikit-learn.

    The defaults are conservative for a 72-month dataset.  Permutation
    importance is calculated on the fitted sample for explanation only; model
    selection remains based on walk-forward out-of-sample error.
    """

    max_iter: int = 120
    learning_rate: float = 0.05
    max_leaf_nodes: int = 15
    min_samples_leaf: int = 6
    l2_regularization: float = 0.1
    random_state: int = 42
    model_: Pipeline = field(init=False, repr=False)
    feature_names_: list[str] = field(init=False)
    feature_importances_: pd.Series = field(init=False)
    requires_features: bool = field(default=True, init=False)

    def fit(self, X: Any, y: Any) -> "HistGradientBoostingForecaster":
        frame = _to_frame(X)
        target = _to_target(y)
        if len(frame) != target.size:
            raise ValueError("X and y must contain the same number of rows.")
        self.feature_names_ = [str(column) for column in frame.columns]
        self.model_ = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "hist_gradient_boosting",
                    HistGradientBoostingRegressor(
                        max_iter=self.max_iter,
                        learning_rate=self.learning_rate,
                        max_leaf_nodes=self.max_leaf_nodes,
                        min_samples_leaf=self.min_samples_leaf,
                        l2_regularization=self.l2_regularization,
                        random_state=self.random_state,
                    ),
                ),
            ]
        )
        self.model_.fit(frame, target)
        importance = permutation_importance(
            self.model_,
            frame,
            target,
            scoring="neg_mean_absolute_error",
            n_repeats=3,
            random_state=self.random_state,
        ).importances_mean
        positive = np.clip(importance, 0.0, None)
        total = positive.sum()
        normalized = positive / total if total > 0 else np.zeros_like(positive)
        self.feature_importances_ = pd.Series(
            normalized,
            index=self.feature_names_,
            name="importance",
        ).sort_values(ascending=False)
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


# Short alias for callers that do not need the implementation name.
TreeForecaster = HistGradientBoostingForecaster
