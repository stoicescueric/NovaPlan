"""Named, management-friendly financial scenarios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from .forecast import build_monthly_forecast


SCENARIO_LIBRARY: dict[str, dict[str, Any]] = {
    "Base": {},
    "Upside": {
        "demand_change_pct": 0.05,
        "utilization_change_pp": 0.03,
        "billing_rate_change_pct": 0.03,
        "dso_delta_days": -5.0,
        "incremental_hires_total": 12,
    },
    "Downside": {
        "demand_change_pct": -0.08,
        "utilization_change_pp": -0.05,
        "dso_delta_days": 12.0,
        "annual_salary_inflation": 0.08,
        "realization_rate_change_pp": -0.01,
    },
    "Hiring Expansion": {
        "incremental_hires_total": 40,
        "hire_joining_months": 6,
        "hire_ramp_months": 3,
        "utilization_change_pp": -0.01,
    },
    "Collections Improvement": {"dso_delta_days": -10.0},
    "Pricing Initiative": {
        "billing_rate_change_pct": 0.05,
        "utilization_change_pp": -0.01,
        "demand_change_pct": -0.01,
    },
    "2026 Expansion Decision": {
        "incremental_hires_total": 40,
        "hire_joining_months": 6,
        "hire_ramp_months": 3,
        "dso_days": 58.0,
    },
    "Risk": {
        "incremental_hires_total": 40,
        "hire_joining_months": 6,
        "hire_ramp_months": 3,
        "dso_days": 70.0,
        "utilization_change_pp": -0.05,
        "annual_salary_inflation": 0.08,
    },
    "Mitigation": {
        "incremental_hires_total": 40,
        "hire_joining_months": 9,
        "hire_ramp_months": 3,
        "dso_days": 50.0,
        "billing_rate_change_pct": 0.02,
    },
    "Custom": {},
}

SCENARIO_ALIASES = {
    "Risk Case": "Risk",
    "Mitigation Case": "Mitigation",
    "Expansion": "2026 Expansion Decision",
    "Custom Scenario": "Custom",
}


def scenario_assumptions(
    scenario_name: str = "Base",
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a safe copy of the selected scenario assumptions."""

    canonical = SCENARIO_ALIASES.get(scenario_name, scenario_name)
    if canonical not in SCENARIO_LIBRARY:
        available = ", ".join(SCENARIO_LIBRARY)
        raise ValueError(f"Unknown scenario {scenario_name!r}. Available: {available}.")
    result = dict(SCENARIO_LIBRARY[canonical])
    if overrides:
        supplied = dict(overrides)
        # The Scenario Lab uses deliberately explicit delta labels. When they
        # are present, layer all sliders on top of the selected preset.
        ui_delta_mode = bool(supplied.pop("_delta_mode", False)) or any(
            key in supplied
            for key in (
                "revenue_demand_change_pct",
                "utilization_delta_pp",
                "incremental_hires",
                "attrition_delta_pp",
                "salary_inflation_delta_pp",
            )
        )
        if ui_delta_mode:
            aliases = {
                "revenue_demand_change_pct": "demand_change_pct",
                "utilization_delta_pp": "utilization_change_pp",
                "incremental_hires": "incremental_hires_total",
            }
            additive = {
                "demand_change_pct",
                "utilization_change_pp",
                "billing_rate_change_pct",
                "incremental_hires_total",
                "attrition_delta_pp",
                "salary_inflation_delta_pp",
                "dso_delta_days",
                "dpo_delta_days",
                "fx_change_pct",
                "capex_change_pct",
                "discretionary_opex_change_pct",
            }
            for key, value in supplied.items():
                canonical_key = aliases.get(key, key)
                if canonical_key in additive and isinstance(value, (int, float)):
                    result[canonical_key] = float(result.get(canonical_key, 0.0)) + float(value)
                else:
                    result[canonical_key] = value
        else:
            result.update(supplied)
    return result


def summarize_forecast(forecast: pd.DataFrame, scenario_name: str = "Base") -> dict[str, Any]:
    """Condense a forecast into the decision metrics used for comparison."""

    if forecast.empty:
        raise ValueError("Forecast cannot be empty.")
    revenue = float(forecast["revenue_eur"].sum())
    ebitda = float(forecast["ebitda_eur"].sum())
    minimum_cash = float(forecast["closing_cash_eur"].min())
    threshold = float(forecast["minimum_cash_threshold_eur"].iloc[-1])
    return {
        "scenario": scenario_name,
        "revenue_eur": revenue,
        "ebitda_eur": ebitda,
        "ebitda_margin": ebitda / revenue if revenue else 0.0,
        "operating_cash_flow_eur": float(forecast["operating_cash_flow_eur"].sum()),
        "year_end_cash_eur": float(forecast["closing_cash_eur"].iloc[-1]),
        "minimum_cash_eur": minimum_cash,
        "liquidity_headroom_eur": minimum_cash - threshold,
        "funding_requirement_eur": max(threshold - minimum_cash, 0.0),
        "headcount": float(forecast["headcount"].iloc[-1]),
        "dso": float(forecast["dso"].mean()),
        "utilization": float(forecast["utilization"].mean()),
    }


def run_scenario(
    history: pd.DataFrame,
    scenario_name: str = "Base",
    overrides: Mapping[str, Any] | None = None,
    months: int = 18,
) -> dict[str, Any]:
    """Run one named scenario and return assumptions, forecast and summary."""

    canonical = SCENARIO_ALIASES.get(scenario_name, scenario_name)
    assumptions = scenario_assumptions(canonical, overrides)
    forecast = build_monthly_forecast(history, months=months, overrides=assumptions)
    return {
        "scenario": canonical,
        "assumptions": assumptions,
        "summary": summarize_forecast(forecast, canonical),
        "forecast": forecast,
    }


def compare_scenarios(
    history: pd.DataFrame,
    scenario_names: Sequence[str] | None = None,
    overrides_by_scenario: Mapping[str, Mapping[str, Any]] | None = None,
    months: int = 18,
) -> pd.DataFrame:
    """Compare scenarios and calculate transparent deltas versus Base."""

    names = list(scenario_names or ("Base", "Upside", "Downside", "Hiring Expansion", "Collections Improvement", "Pricing Initiative"))
    if "Base" not in names:
        names.insert(0, "Base")
    overrides_by_scenario = overrides_by_scenario or {}
    summaries = [
        run_scenario(
            history,
            scenario_name=name,
            overrides=overrides_by_scenario.get(name),
            months=months,
        )["summary"]
        for name in names
    ]
    result = pd.DataFrame(summaries)
    base = result.loc[result["scenario"].eq("Base")].iloc[0]
    for metric in (
        "revenue_eur",
        "ebitda_eur",
        "operating_cash_flow_eur",
        "year_end_cash_eur",
        "minimum_cash_eur",
        "funding_requirement_eur",
        "headcount",
        "dso",
        "utilization",
    ):
        result[f"delta_{metric}_vs_base"] = result[metric] - float(base[metric])
    return result


def expansion_decision_cases(history: pd.DataFrame, months: int = 18) -> pd.DataFrame:
    """Run the preloaded expansion, risk and mitigation cases together."""

    return compare_scenarios(
        history,
        scenario_names=("Base", "2026 Expansion Decision", "Risk", "Mitigation"),
        months=months,
    )
