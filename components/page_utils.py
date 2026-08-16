"""Defensive adapters between the analytical engine and presentation layer."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def first_column(frame: pd.DataFrame, names: Iterable[str], default: float = 0.0) -> pd.Series:
    """Return the first available candidate column as a numeric series."""
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    return pd.Series(np.full(len(frame), default), index=frame.index, dtype=float)


def first_date_column(frame: pd.DataFrame, names: Iterable[str]) -> pd.Series:
    """Return the first date-like candidate column as timestamps."""
    for name in names:
        if name in frame.columns:
            return pd.to_datetime(frame[name], errors="coerce")
    return pd.Series(pd.date_range("2026-01-31", periods=max(len(frame), 1), freq="ME")[: len(frame)])


def summary_value(summary: dict, *keys: str, default: float = 0.0) -> float:
    """Read the first matching value from a scenario/Monte Carlo summary."""
    for key in keys:
        if key in summary and summary[key] is not None:
            try:
                return float(summary[key])
            except (TypeError, ValueError):
                continue
    return float(default)


def normalize_ratio(value: float) -> float:
    """Normalize percentages supplied either as decimals or whole percentages."""
    number = float(value)
    return number / 100 if abs(number) > 1.5 else number


def safe_delta(current: float, previous: float) -> float:
    """Calculate a safe relative delta when the prior value may be zero."""
    if abs(previous) < 1e-9:
        return 0.0
    return current / previous - 1.0
