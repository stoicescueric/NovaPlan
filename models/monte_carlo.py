"""Vectorized Monte Carlo risk simulation over uncertain business drivers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ._utils import last_value, merge_options, sorted_monthly
from .forecast import build_monthly_forecast
from .working_capital import AVERAGE_DAYS_PER_MONTH


DEFAULT_MONTE_CARLO_OPTIONS: dict[str, Any] = {
    "months": 18,
    "ebitda_margin_target": 0.10,
    # A single teaching control that widens or narrows every random driver.
    # 0.0 gives the deterministic forecast; 1.0 keeps the calibrated defaults.
    "uncertainty_scale": 1.0,
    "utilization_monthly_std_pp": 0.018,
    "dso_monthly_std_days": 4.0,
    "billing_realization_std_pct": 0.015,
    "annual_salary_inflation_std_pp": 0.018,
    "annual_attrition_std_pp": 0.02,
    "backlog_conversion_std_pct": 0.04,
    "fx_std_pct": 0.015,
    "macro_persistence": 0.70,
    "forecast_overrides": None,
}


def _correlation(x: np.ndarray, y: np.ndarray) -> float:
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def run_monte_carlo(
    history: pd.DataFrame,
    n_simulations: int = 10_000,
    seed: int = 42,
    threshold: float = 3_000_000.0,
    assumptions: Mapping[str, Any] | None = None,
    ebitda_margin_target: float | None = None,
) -> dict[str, Any]:
    """Simulate correlated drivers and propagate them through cash generation.

    Final cash is never sampled directly. Utilization, payment timing, billing
    realization, attrition, salary inflation, backlog conversion and FX first
    change revenue/cost/working-capital mechanics, which then create cash.
    """

    if n_simulations <= 0:
        raise ValueError("n_simulations must be positive.")
    options = merge_options(DEFAULT_MONTE_CARLO_OPTIONS, assumptions)
    if ebitda_margin_target is not None:
        options["ebitda_margin_target"] = float(ebitda_margin_target)
    months = int(options["months"])
    if months <= 0:
        raise ValueError("months must be positive.")
    uncertainty_scale = float(options.get("uncertainty_scale", 1.0))
    if not np.isfinite(uncertainty_scale) or uncertainty_scale < 0:
        raise ValueError("uncertainty_scale must be a finite non-negative number.")
    rng = np.random.default_rng(seed)
    base = build_monthly_forecast(
        history,
        months=months,
        overrides=options.get("forecast_overrides"),
    )
    clean_history = sorted_monthly(history)

    shape = (n_simulations, months)
    scenario_macro = rng.normal(size=(n_simulations, 1))
    macro_noise = rng.normal(size=shape)
    macro_path = np.zeros(shape)
    persistence = float(options["macro_persistence"])
    macro_path[:, 0] = 0.65 * scenario_macro[:, 0] + 0.35 * macro_noise[:, 0]
    for month_index in range(1, months):
        macro_path[:, month_index] = (
            persistence * macro_path[:, month_index - 1]
            + (1.0 - persistence) * macro_noise[:, month_index]
        )

    base_utilization = base["utilization"].to_numpy(float)[None, :]
    utilization = np.clip(
        base_utilization
        + uncertainty_scale * 0.012 * macro_path
        + rng.normal(
            0.0,
            uncertainty_scale * float(options["utilization_monthly_std_pp"]),
            size=shape,
        ),
        0.55,
        0.90,
    )
    utilization_factor = utilization / np.maximum(base_utilization, 0.01)

    base_dso = base["dso"].to_numpy(float)[None, :]
    dso = np.clip(
        base_dso
        - uncertainty_scale * 3.0 * macro_path
        + rng.normal(
            0.0,
            uncertainty_scale * float(options["dso_monthly_std_days"]),
            size=shape,
        ),
        30.0,
        95.0,
    )

    billing_factor = np.clip(
        1.0
        + uncertainty_scale * 0.006 * macro_path
        + rng.normal(
            0.0,
            uncertainty_scale * float(options["billing_realization_std_pct"]),
            size=shape,
        ),
        0.90,
        1.08,
    )
    salary_inflation_shock = np.clip(
        rng.normal(
            0.0,
            uncertainty_scale * float(options["annual_salary_inflation_std_pp"]),
            size=(n_simulations, 1),
        ),
        -0.05,
        0.08,
    )
    attrition_shock = np.clip(
        -uncertainty_scale * 0.005 * scenario_macro
        + rng.normal(
            0.0,
            uncertainty_scale * float(options["annual_attrition_std_pp"]),
            size=(n_simulations, 1),
        ),
        -0.06,
        0.08,
    )
    backlog_factor = np.clip(
        1.0
        + uncertainty_scale * 0.025 * macro_path
        + rng.normal(
            0.0,
            uncertainty_scale * float(options["backlog_conversion_std_pct"]),
            size=shape,
        ),
        0.82,
        1.18,
    )
    fx_shock = np.clip(
        rng.normal(
            0.0,
            uncertainty_scale * float(options["fx_std_pct"]),
            size=(n_simulations, 1),
        ),
        -0.05,
        0.05,
    )

    elapsed_years = np.arange(1, months + 1, dtype=float)[None, :] / 12.0
    headcount_factor = np.exp(-attrition_shock * elapsed_years)
    demand_factor = np.clip(
        1.0 + uncertainty_scale * 0.02 * macro_path,
        0.90,
        1.10,
    )
    revenue = (
        base["revenue_eur"].to_numpy(float)[None, :]
        * utilization_factor
        * billing_factor
        * backlog_factor
        * demand_factor
        * headcount_factor
    )
    salary_factor = np.maximum((1.0 + salary_inflation_shock) ** elapsed_years, 0.85)
    payroll = (
        base["payroll_eur"].to_numpy(float)[None, :]
        * headcount_factor
        * salary_factor
        / np.maximum(1.0 + fx_shock, 0.90)
    )
    base_revenue = np.maximum(base["revenue_eur"].to_numpy(float)[None, :], 1.0)
    revenue_ratio = revenue / base_revenue
    contractor = base["contractor_cost_eur"].to_numpy(float)[None, :] * (
        0.35 + 0.65 * revenue_ratio
    )
    other_opex = base["other_opex_eur"].to_numpy(float)[None, :] * (
        1.0 + 0.25 * salary_inflation_shock * elapsed_years
    )
    ebitda = revenue - payroll - contractor - other_opex
    depreciation = base["depreciation_eur"].to_numpy(float)[None, :]
    tax = np.maximum(ebitda - depreciation, 0.0) * 0.16

    accounts_receivable = revenue * dso / AVERAGE_DAYS_PER_MONTH
    vendor_expenses = contractor + other_opex
    base_dpo = base["dpo"].to_numpy(float)[None, :]
    accounts_payable = vendor_expenses * base_dpo / AVERAGE_DAYS_PER_MONTH
    opening_ar = last_value(
        clean_history,
        ("accounts_receivable_eur",),
        float(base["accounts_receivable_eur"].iloc[0]),
    )
    opening_ap = last_value(
        clean_history,
        ("accounts_payable_eur",),
        float(base["accounts_payable_eur"].iloc[0]),
    )
    beginning_ar = np.concatenate(
        [np.full((n_simulations, 1), opening_ar), accounts_receivable[:, :-1]], axis=1
    )
    beginning_ap = np.concatenate(
        [np.full((n_simulations, 1), opening_ap), accounts_payable[:, :-1]], axis=1
    )
    change_ar = accounts_receivable - beginning_ar
    change_ap = accounts_payable - beginning_ap
    operating_cash_flow = ebitda - tax - change_ar + change_ap
    capex = base["capex_eur"].to_numpy(float)[None, :]
    free_cash_flow = operating_cash_flow - capex
    opening_cash = float(base["opening_cash_eur"].iloc[0])
    cash_trajectories = opening_cash + np.cumsum(free_cash_flow, axis=1)

    year_end_cash = cash_trajectories[:, -1]
    minimum_cash = cash_trajectories.min(axis=1)
    total_revenue = revenue.sum(axis=1)
    total_ebitda = ebitda.sum(axis=1)
    ebitda_margin = np.divide(
        total_ebitda,
        total_revenue,
        out=np.zeros(n_simulations),
        where=total_revenue != 0,
    )
    percentiles = np.percentile(year_end_cash, [5, 25, 50, 75, 95])
    shortfall_to_threshold = np.maximum(float(threshold) - minimum_cash, 0.0)
    external_funding_need = np.maximum(-minimum_cash, 0.0)
    target_margin = float(options["ebitda_margin_target"])
    summary = {
        "expected_year_end_cash_eur": float(year_end_cash.mean()),
        "median_year_end_cash_eur": float(percentiles[2]),
        "p5_year_end_cash_eur": float(percentiles[0]),
        "p25_year_end_cash_eur": float(percentiles[1]),
        "p75_year_end_cash_eur": float(percentiles[3]),
        "p95_year_end_cash_eur": float(percentiles[4]),
        "probability_cash_below_threshold": float(np.mean(minimum_cash < threshold)),
        "probability_external_funding_required": float(np.mean(minimum_cash < 0.0)),
        "expected_maximum_funding_need_eur": float(external_funding_need.mean()),
        "expected_shortfall_to_threshold_eur": float(shortfall_to_threshold.mean()),
        "probability_ebitda_margin_below_target": float(np.mean(ebitda_margin < target_margin)),
        "minimum_cash_threshold_eur": float(threshold),
        "ebitda_margin_target": target_margin,
        "uncertainty_scale": uncertainty_scale,
        "n_simulations": int(n_simulations),
        "seed": int(seed),
    }
    summary.update(
        {
            "probability_below_threshold": summary["probability_cash_below_threshold"],
            "p_cash_below_threshold": summary["probability_cash_below_threshold"],
            "probability_funding_required": summary["probability_external_funding_required"],
            "p_external_funding_required": summary["probability_external_funding_required"],
            "p_ebitda_margin_below_target": summary["probability_ebitda_margin_below_target"],
        }
    )

    fan_values = np.percentile(cash_trajectories, [5, 25, 50, 75, 95], axis=0)
    fan_chart = pd.DataFrame(
        {
            "month": base["month"],
            "p5_cash_eur": fan_values[0],
            "p25_cash_eur": fan_values[1],
            "p50_cash_eur": fan_values[2],
            "p75_cash_eur": fan_values[3],
            "p95_cash_eur": fan_values[4],
        }
    )
    fan_chart["p5"] = fan_chart["p5_cash_eur"]
    fan_chart["p25"] = fan_chart["p25_cash_eur"]
    fan_chart["p50"] = fan_chart["p50_cash_eur"]
    fan_chart["p75"] = fan_chart["p75_cash_eur"]
    fan_chart["p95"] = fan_chart["p95_cash_eur"]
    histogram_count, histogram_edges = np.histogram(year_end_cash, bins=40)
    histogram = pd.DataFrame(
        {
            "bin_start_eur": histogram_edges[:-1],
            "bin_end_eur": histogram_edges[1:],
            "simulation_count": histogram_count,
        }
    )

    driver_series = {
        "Utilization": (utilization - base_utilization).mean(axis=1),
        "DSO": (dso - base_dso).mean(axis=1),
        "Billing realization": (billing_factor - 1.0).mean(axis=1),
        "Salary inflation": salary_inflation_shock[:, 0],
        "Attrition": attrition_shock[:, 0],
        "Backlog conversion": (backlog_factor - 1.0).mean(axis=1),
        "EUR/RON": fx_shock[:, 0],
    }
    ranking_rows = []
    for driver, samples in driver_series.items():
        correlation = _correlation(samples, year_end_cash)
        ranking_rows.append(
            {
                "driver": driver,
                "correlation_with_year_end_cash": correlation,
                "absolute_correlation": abs(correlation),
                "direction": "Increases cash" if correlation > 0 else "Reduces cash",
            }
        )
    risk_driver_ranking = pd.DataFrame(ranking_rows).sort_values(
        "absolute_correlation", ascending=False
    ).reset_index(drop=True)
    risk_driver_ranking["rank"] = np.arange(1, len(risk_driver_ranking) + 1)
    risk_driver_ranking["correlation"] = risk_driver_ranking[
        "correlation_with_year_end_cash"
    ]
    risk_driver_ranking["importance"] = risk_driver_ranking["absolute_correlation"]

    return {
        "summary": summary,
        "base_forecast": base,
        "fan_chart": fan_chart,
        "histogram": histogram,
        "year_end_cash_eur": year_end_cash,
        "minimum_cash_eur": minimum_cash,
        "cash_trajectories_eur": cash_trajectories,
        "ebitda_margin": ebitda_margin,
        "risk_driver_ranking": risk_driver_ranking,
        "simulation_assumptions": dict(options),
    }


# Compact alias.
simulate = run_monte_carlo
