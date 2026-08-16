"""Deterministic driver sensitivity and tornado-chart inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from .forecast import build_monthly_forecast
from .scenarios import summarize_forecast


DEFAULT_SENSITIVITY_SHOCKS: dict[str, tuple[dict[str, Any], dict[str, Any], str, str]] = {
    "DSO": (
        {"dso_delta_days": -10.0},
        {"dso_delta_days": 10.0},
        "-10 days",
        "+10 days",
    ),
    "Utilization": (
        {"utilization_change_pp": -0.05},
        {"utilization_change_pp": 0.05},
        "-5 pp",
        "+5 pp",
    ),
    "Billing Rate": (
        {"billing_rate_change_pct": -0.05},
        {"billing_rate_change_pct": 0.05},
        "-5%",
        "+5%",
    ),
    "Salary Cost": (
        {"salary_cost_change_pct": -0.05},
        {"salary_cost_change_pct": 0.05},
        "-5%",
        "+5%",
    ),
    "Attrition": (
        {"annual_attrition_rate": 0.09},
        {"annual_attrition_rate": 0.13},
        "9% annual",
        "13% annual",
    ),
    "EUR/RON": (
        {"eur_ron_change_pct": -0.03},
        {"eur_ron_change_pct": 0.03},
        "-3%",
        "+3%",
    ),
    "Capex": (
        {"capex_change_pct": -0.20},
        {"capex_change_pct": 0.20},
        "-20%",
        "+20%",
    ),
}


def run_sensitivity(
    history: pd.DataFrame,
    shocks: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any], str, str]] | None = None,
    months: int = 18,
    base_overrides: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Shock one major driver at a time and rank its financial materiality."""

    shock_library = dict(shocks or DEFAULT_SENSITIVITY_SHOCKS)
    base_options = dict(base_overrides or {})
    base_forecast = build_monthly_forecast(history, months=months, overrides=base_options)
    base = summarize_forecast(base_forecast, "Base")
    rows: list[dict[str, Any]] = []

    for driver, definition in shock_library.items():
        if len(definition) != 4:
            raise ValueError(
                f"Sensitivity definition for {driver!r} must be (low overrides, high overrides, low label, high label)."
            )
        low_overrides, high_overrides, low_label, high_label = definition
        for direction, label, driver_overrides in (
            ("Low", low_label, low_overrides),
            ("High", high_label, high_overrides),
        ):
            options = dict(base_options)
            options.update(dict(driver_overrides))
            forecast = build_monthly_forecast(history, months=months, overrides=options)
            summary = summarize_forecast(forecast, f"{driver} {label}")
            rows.append(
                {
                    "driver": driver,
                    "direction": direction,
                    "shock": label,
                    "ebitda_impact_eur": summary["ebitda_eur"] - base["ebitda_eur"],
                    "minimum_cash_impact_eur": summary["minimum_cash_eur"] - base["minimum_cash_eur"],
                    "year_end_cash_impact_eur": summary["year_end_cash_eur"] - base["year_end_cash_eur"],
                    "cash_impact_eur": summary["year_end_cash_eur"] - base["year_end_cash_eur"],
                    "scenario_ebitda_eur": summary["ebitda_eur"],
                    "scenario_minimum_cash_eur": summary["minimum_cash_eur"],
                    "scenario_year_end_cash_eur": summary["year_end_cash_eur"],
                }
            )

    result = pd.DataFrame(rows)
    materiality = (
        result.assign(
            _materiality=result[
                ["ebitda_impact_eur", "minimum_cash_impact_eur", "year_end_cash_impact_eur"]
            ].abs().max(axis=1)
        )
        .groupby("driver")["_materiality"]
        .max()
        .sort_values(ascending=False)
    )
    ranks = pd.Series(np.arange(1, len(materiality) + 1), index=materiality.index)
    result["economic_materiality_eur"] = result["driver"].map(materiality)
    result["rank"] = result["driver"].map(ranks).astype(int)
    result = result.sort_values(["rank", "direction"], ascending=[True, False]).reset_index(drop=True)
    result.attrs["base_summary"] = base
    return result


def tornado_summary(sensitivity: pd.DataFrame, metric: str = "year_end_cash_impact_eur") -> pd.DataFrame:
    """Pivot the long sensitivity output into one low/high row per driver."""

    if metric not in sensitivity:
        raise ValueError(f"Unknown sensitivity metric {metric!r}.")
    pivot = sensitivity.pivot(index="driver", columns="direction", values=metric).reset_index()
    ranks = sensitivity.groupby("driver")["rank"].min()
    pivot["rank"] = pivot["driver"].map(ranks)
    return pivot.sort_values("rank").reset_index(drop=True)
