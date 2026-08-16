"""Small shared helpers for the NovaPlan analytical models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd


def merge_options(defaults: Mapping[str, Any], overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a shallow, non-mutating assumptions merge."""

    merged = dict(defaults)
    if overrides:
        merged.update(dict(overrides))
    return merged


def month_column(frame: pd.DataFrame) -> str:
    """Find the time column used by a monthly dataset."""

    for candidate in ("month", "date", "period", "period_end"):
        if candidate in frame.columns:
            return candidate
    raise ValueError("Monthly data must contain a 'month' (or date/period) column.")


def sorted_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy, normalize and sort a monthly dataframe."""

    if frame.empty:
        raise ValueError("Monthly history cannot be empty.")
    result = frame.copy()
    source = month_column(result)
    result["month"] = pd.to_datetime(result[source]).dt.to_period("M").dt.to_timestamp()
    return result.sort_values("month").reset_index(drop=True)


def first_existing(frame: pd.DataFrame, names: Sequence[str]) -> str | None:
    """Return the first column name present in *frame*."""

    return next((name for name in names if name in frame.columns), None)


def recent_mean(
    frame: pd.DataFrame,
    names: Sequence[str],
    default: float,
    periods: int = 6,
) -> float:
    """Read a finite recent average from the first matching column."""

    column = first_existing(frame, names)
    if column is None:
        return float(default)
    values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    value = values.tail(periods).mean()
    return float(default if pd.isna(value) else value)


def last_value(frame: pd.DataFrame, names: Sequence[str], default: float) -> float:
    """Read the last finite numeric value from the first matching column."""

    column = first_existing(frame, names)
    if column is None:
        return float(default)
    values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(default if values.empty else values.iloc[-1])


def monthly_values(value: Any, months: int, default: float = 0.0) -> np.ndarray:
    """Expand a scalar or short sequence to an array of *months* values."""

    if value is None:
        return np.full(months, float(default), dtype=float)
    if np.isscalar(value) and not isinstance(value, str):
        return np.full(months, float(value), dtype=float)
    values = np.asarray(list(value), dtype=float).reshape(-1)
    if values.size == 0:
        return np.full(months, float(default), dtype=float)
    if values.size < months:
        values = np.pad(values, (0, months - values.size), mode="edge")
    return values[:months]


def business_days_in_month(month: pd.Timestamp) -> int:
    """Count Monday-Friday days; public holidays are intentionally not assumed."""

    start = np.datetime64(pd.Timestamp(month).date())
    end = np.datetime64((pd.Timestamp(month) + pd.offsets.MonthBegin(1)).date())
    return int(np.busday_count(start, end))


def safe_divide(numerator: Any, denominator: Any, default: float = 0.0) -> Any:
    """Divide scalars/arrays without propagating divide-by-zero noise."""

    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.divide(numerator, denominator)
    if np.isscalar(result):
        return float(result) if np.isfinite(result) else float(default)
    return np.where(np.isfinite(result), result, default)


def validate_fraction(name: str, value: float, *, upper: float = 1.0) -> None:
    """Raise a clear error for an invalid rate/fraction."""

    if not 0.0 <= value <= upper:
        raise ValueError(f"{name} must be between 0 and {upper:g}; received {value!r}.")
