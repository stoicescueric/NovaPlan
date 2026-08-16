"""Operationally driven 18-month rolling forecast."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ._utils import (
    business_days_in_month,
    last_value,
    merge_options,
    monthly_values,
    recent_mean,
    sorted_monthly,
)
from .working_capital import AVERAGE_DAYS_PER_MONTH, calculate_ap, calculate_ar


@dataclass(frozen=True, slots=True)
class ForecastAssumptions:
    """Main management and external assumptions for the rolling forecast."""

    annual_demand_growth: float = 0.05
    annual_billing_rate_growth: float = 0.03
    annual_salary_inflation: float = 0.06
    annual_attrition_rate: float = 0.11
    utilization_change_pp: float = 0.0
    billing_rate_change_pct: float = 0.0
    salary_cost_change_pct: float = 0.0
    dso_delta_days: float = 0.0
    dpo_delta_days: float = 0.0
    incremental_hires_total: int = 0
    hire_joining_months: int = 6
    hire_ramp_months: int = 3
    discretionary_opex_change_pct: float = 0.0
    contractor_cost_change_pct: float = 0.0
    capex_change_pct: float = 0.0
    eur_ron_change_pct: float = 0.0


DEFAULT_FORECAST_OPTIONS: dict[str, Any] = {
    "annual_demand_growth": 0.05,
    "annual_billing_rate_growth": 0.03,
    "annual_salary_inflation": 0.06,
    "annual_other_opex_inflation": 0.035,
    "annual_attrition_rate": None,
    "baseline_new_hires_per_month": None,
    "utilization_change_pp": 0.0,
    "billing_rate_change_pct": 0.0,
    "salary_cost_change_pct": 0.0,
    "realization_rate_change_pp": 0.0,
    "demand_change_pct": 0.0,
    "backlog_conversion_change_pct": 0.0,
    "dso_days": None,
    "dso_delta_days": 0.0,
    "dpo_days": None,
    "dpo_delta_days": 0.0,
    "incremental_hires_total": 0,
    "hire_joining_months": 6,
    "hire_ramp_months": 3,
    "recruiting_cost_per_hire_eur": 3_000.0,
    "equipment_cost_per_hire_eur": 1_800.0,
    "discretionary_opex_change_pct": 0.0,
    "contractor_cost_change_pct": 0.0,
    "capex_change_pct": 0.0,
    "eur_ron_change_pct": 0.0,
    "tax_rate": 0.16,
    "minimum_cash_threshold_eur": 3_000_000.0,
    "management_revenue_adjustment_eur": 0.0,
    "management_revenue_adjustment_pct": 0.0,
    "adjustment_rationale": "No management adjustment",
    "hours_per_day": 8.0,
    "utilization_floor": 0.55,
    "utilization_ceiling": 0.90,
}


def _normalize_overrides(overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Accept concise UI labels as aliases for canonical model assumptions."""

    values = dict(overrides or {})
    aliases = {
        "utilization_change": "utilization_change_pp",
        "utilization_delta": "utilization_change_pp",
        "utilization_delta_pp": "utilization_change_pp",
        "billing_rate_change": "billing_rate_change_pct",
        "pricing_change_pct": "billing_rate_change_pct",
        "revenue_demand_change_pct": "demand_change_pct",
        "salary_change_pct": "salary_cost_change_pct",
        "salary_inflation": "annual_salary_inflation",
        "dso": "dso_days",
        "dpo": "dpo_days",
        "dso_change_days": "dso_delta_days",
        "dpo_change_days": "dpo_delta_days",
        "new_hires": "incremental_hires_total",
        "incremental_hires": "incremental_hires_total",
        "joining_months": "hire_joining_months",
        "hiring_stagger_months": "hire_joining_months",
        "ramp_up_months": "hire_ramp_months",
        "capex_change": "capex_change_pct",
        "fx_change_pct": "eur_ron_change_pct",
    }
    for alias, canonical in aliases.items():
        if alias in values and canonical not in values:
            values[canonical] = values[alias]
    return values


def _seasonality(history: pd.DataFrame, base_utilization: float) -> dict[int, float]:
    if "utilization" in history and len(history) >= 12:
        values = pd.to_numeric(history["utilization"], errors="coerce")
        overall = values.tail(24).mean()
        seasonal = history.assign(_util=values).tail(36).groupby(history["month"].tail(36).dt.month)["_util"].mean()
        if np.isfinite(overall) and overall > 0:
            result = {int(key): float(np.clip(value / overall, 0.88, 1.08)) for key, value in seasonal.items()}
        else:
            result = {}
    else:
        result = {}
    defaults = {7: 0.95, 8: 0.91, 12: 0.93}
    for month, factor in defaults.items():
        result.setdefault(month, factor)
    return {month: result.get(month, 1.0) for month in range(1, 13)}


def _revenue_calibration(history: pd.DataFrame, hours_per_day: float) -> float:
    required = {
        "headcount",
        "billable_share",
        "working_days",
        "utilization",
        "billing_rate_eur",
        "revenue_eur",
    }
    if not required.issubset(history.columns):
        return 1.0
    sample = history.tail(12)
    raw = (
        pd.to_numeric(sample["headcount"], errors="coerce")
        * pd.to_numeric(sample["billable_share"], errors="coerce")
        * pd.to_numeric(sample["working_days"], errors="coerce")
        * hours_per_day
        * pd.to_numeric(sample["utilization"], errors="coerce")
        * pd.to_numeric(sample["billing_rate_eur"], errors="coerce")
        * pd.to_numeric(sample.get("realization_rate", 0.97), errors="coerce")
    )
    ratios = pd.to_numeric(sample["revenue_eur"], errors="coerce") / raw.replace(0, np.nan)
    calibration = ratios.replace([np.inf, -np.inf], np.nan).dropna().median()
    return float(np.clip(calibration, 0.50, 1.50)) if np.isfinite(calibration) else 1.0


def _distributed_hires(total: int, joining_months: int, months: int) -> np.ndarray:
    result = np.zeros(months, dtype=float)
    if total <= 0:
        return result
    spread = max(1, min(int(joining_months), months))
    result[:spread] = total // spread
    result[: total % spread] += 1
    return result


def _ramped_hire_fte(hires: np.ndarray, ramp_months: int) -> np.ndarray:
    result = np.zeros(len(hires))
    for join_index, cohort in enumerate(hires):
        if cohort <= 0:
            continue
        age = np.arange(1, len(hires) - join_index + 1, dtype=float)
        ramp = np.ones_like(age) if ramp_months <= 0 else np.minimum(age / ramp_months, 1.0)
        result[join_index:] += cohort * ramp
    return result


def build_monthly_forecast(
    history: pd.DataFrame,
    months: int = 18,
    overrides: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build an explainable monthly forecast from operational assumptions.

    The returned dataframe preserves separate model-baseline, management
    adjustment and final revenue columns for forecast governance.
    """

    if months <= 0:
        raise ValueError("months must be positive.")
    options = merge_options(DEFAULT_FORECAST_OPTIONS, _normalize_overrides(overrides))
    actuals = sorted_monthly(history)
    dates = pd.date_range(actuals["month"].iloc[-1] + pd.offsets.MonthBegin(1), periods=months, freq="MS")
    step = np.arange(1, months + 1, dtype=float)

    starting_headcount = last_value(actuals, ("headcount",), 275.0)
    base_billable_share = recent_mean(actuals, ("billable_share",), 0.82, periods=12)
    base_utilization = recent_mean(actuals, ("utilization",), 0.74, periods=12)
    base_realization = recent_mean(actuals, ("realization_rate",), 0.97, periods=12)
    base_rate = last_value(actuals, ("billing_rate_eur",), 65.0)
    base_dso = recent_mean(actuals, ("dso", "dso_days"), 55.0, periods=6)
    base_dpo = recent_mean(actuals, ("dpo", "dpo_days"), 35.0, periods=6)
    base_fx = last_value(actuals, ("eur_ron",), 4.97)

    historical_attrition_rate = recent_mean(actuals, ("attrition",), 0.0, periods=12) * 12.0 / max(starting_headcount, 1.0)
    annual_attrition_rate = options["annual_attrition_rate"]
    if annual_attrition_rate is None:
        annual_attrition_rate = float(np.clip(historical_attrition_rate or 0.11, 0.04, 0.25))
    annual_attrition_rate = max(
        float(annual_attrition_rate) + float(options.get("attrition_delta_pp", 0.0)), 0.0
    )
    baseline_hires = options["baseline_new_hires_per_month"]
    if baseline_hires is None:
        baseline_hires = recent_mean(actuals, ("new_hires", "hires"), starting_headcount * 0.11 / 12.0, periods=6)
    base_hire_schedule = monthly_values(baseline_hires, months, float(baseline_hires))
    incremental_hires = _distributed_hires(
        int(options.get("incremental_hires_total", 0)),
        int(options.get("hire_joining_months", 6)),
        months,
    )
    new_hires = np.maximum(base_hire_schedule + incremental_hires, 0.0)

    headcount = np.zeros(months)
    attrition = np.zeros(months)
    prior_headcount = starting_headcount
    for index in range(months):
        attrition[index] = prior_headcount * float(annual_attrition_rate) / 12.0
        headcount[index] = max(prior_headcount + new_hires[index] - attrition[index], 1.0)
        prior_headcount = headcount[index]

    cumulative_attrition = np.cumsum(attrition)
    ramped_fte = _ramped_hire_fte(new_hires, int(options.get("hire_ramp_months", 3)))
    revenue_headcount = np.maximum(starting_headcount - cumulative_attrition + ramped_fte, 1.0)
    seasonality = _seasonality(actuals, base_utilization)
    seasonal_factor = np.array([seasonality[date.month] for date in dates])

    if options.get("utilization") is not None:
        utilization_anchor = float(options["utilization"])
    else:
        utilization_anchor = base_utilization
    demand_growth = (1.0 + float(options["annual_demand_growth"])) ** (step / 12.0)
    demand_utilization_lift = (demand_growth - 1.0) * 0.15
    utilization = (
        utilization_anchor * seasonal_factor
        + float(options.get("utilization_change_pp", 0.0))
        + demand_utilization_lift
    )
    utilization = np.clip(
        utilization,
        float(options["utilization_floor"]),
        float(options["utilization_ceiling"]),
    )
    billable_share = np.clip(
        monthly_values(options.get("billable_share"), months, base_billable_share), 0.70, 0.92
    )
    working_days = np.array([business_days_in_month(date) for date in dates], dtype=float)

    if options.get("billing_rate_eur") is not None:
        rate_start = float(options["billing_rate_eur"])
    else:
        rate_start = base_rate
    billing_rate = (
        rate_start
        * (1.0 + float(options["annual_billing_rate_growth"])) ** (step / 12.0)
        * (1.0 + float(options.get("billing_rate_change_pct", 0.0)))
    )
    realization = np.clip(
        base_realization + float(options.get("realization_rate_change_pp", 0.0)), 0.85, 1.02
    )
    calibration = _revenue_calibration(actuals, float(options["hours_per_day"]))
    demand_factor = (
        demand_growth
        * (1.0 + float(options.get("demand_change_pct", 0.0)))
        * (1.0 + float(options.get("backlog_conversion_change_pct", 0.0)))
    )
    capacity_hours = revenue_headcount * billable_share * working_days * float(options["hours_per_day"])
    billable_hours = capacity_hours * utilization
    model_revenue = billable_hours * billing_rate * realization * calibration * demand_factor
    adjustment_eur = monthly_values(options.get("management_revenue_adjustment_eur"), months, 0.0)
    adjustment_pct = monthly_values(options.get("management_revenue_adjustment_pct"), months, 0.0)
    management_adjustment = adjustment_eur + model_revenue * adjustment_pct
    revenue = np.maximum(model_revenue + management_adjustment, 0.0)

    payroll_per_fte = recent_mean(
        actuals.assign(
            _payroll_per_fte=pd.to_numeric(actuals.get("payroll_eur", pd.Series(index=actuals.index, dtype=float)), errors="coerce")
            / pd.to_numeric(actuals.get("headcount", pd.Series(index=actuals.index, dtype=float)), errors="coerce").replace(0, np.nan)
        ),
        ("_payroll_per_fte",),
        3_500.0,
        periods=6,
    )
    fx_change = float(options.get("eur_ron_change_pct", 0.0))
    effective_salary_inflation = float(options["annual_salary_inflation"]) + float(
        options.get("salary_inflation_delta_pp", 0.0)
    )
    salary_factor = (
        (1.0 + effective_salary_inflation) ** (step / 12.0)
        * (1.0 + float(options.get("salary_cost_change_pct", 0.0)))
        / max(1.0 + fx_change, 0.1)
    )
    payroll = headcount * payroll_per_fte * salary_factor
    recruiting_cost = new_hires * float(options["recruiting_cost_per_hire_eur"])

    historical_revenue = pd.to_numeric(actuals["revenue_eur"], errors="coerce").replace(0, np.nan)
    contractor_ratio = recent_mean(
        actuals.assign(
            _contractor_ratio=pd.to_numeric(actuals.get("contractor_cost_eur", 0.0), errors="coerce") / historical_revenue
        ),
        ("_contractor_ratio",),
        0.08,
        periods=6,
    )
    contractor_cost = revenue * contractor_ratio * (1.0 + float(options["contractor_cost_change_pct"]))
    recent_other_opex = recent_mean(actuals, ("other_opex_eur",), 300_000.0, periods=6)
    fixed_opex = recent_other_opex * 0.60 * (
        1.0 + float(options["annual_other_opex_inflation"])
    ) ** (step / 12.0)
    historical_other_ratio = recent_mean(
        actuals.assign(
            _other_ratio=pd.to_numeric(actuals.get("other_opex_eur", 0.0), errors="coerce") / historical_revenue
        ),
        ("_other_ratio",),
        0.12,
        periods=6,
    )
    variable_opex = revenue * historical_other_ratio * 0.40
    other_opex = (
        (fixed_opex + variable_opex)
        * (1.0 + float(options["discretionary_opex_change_pct"]))
        + recruiting_cost
    )
    ebitda = revenue - payroll - contractor_cost - other_opex
    ebitda_margin = np.divide(ebitda, revenue, out=np.zeros(months), where=revenue != 0)

    historical_capex_ratio = recent_mean(
        actuals.assign(
            _capex_ratio=pd.to_numeric(actuals.get("capex_eur", 0.0), errors="coerce") / historical_revenue
        ),
        ("_capex_ratio",),
        0.018,
        periods=12,
    )
    capex = (
        revenue * historical_capex_ratio * (1.0 + float(options["capex_change_pct"]))
        + new_hires * float(options["equipment_cost_per_hire_eur"])
    )
    depreciation = recent_mean(actuals, ("depreciation_eur",), 25_000.0, periods=6) + capex / 36.0

    dso_anchor = base_dso if options.get("dso_days") is None else float(options["dso_days"])
    dpo_anchor = base_dpo if options.get("dpo_days") is None else float(options["dpo_days"])
    dso = np.clip(monthly_values(dso_anchor + float(options["dso_delta_days"]), months), 20.0, 120.0)
    dpo = np.clip(monthly_values(dpo_anchor + float(options["dpo_delta_days"]), months), 10.0, 120.0)
    accounts_receivable = calculate_ar(revenue, dso)
    vendor_expenses = contractor_cost + other_opex
    accounts_payable = calculate_ap(vendor_expenses, dpo)
    opening_ar = last_value(actuals, ("accounts_receivable_eur",), float(accounts_receivable[0]))
    opening_ap = last_value(actuals, ("accounts_payable_eur",), float(accounts_payable[0]))
    beginning_ar = np.r_[opening_ar, accounts_receivable[:-1]]
    beginning_ap = np.r_[opening_ap, accounts_payable[:-1]]
    collections = np.maximum(beginning_ar + revenue - accounts_receivable, 0.0)
    vendor_payments = np.maximum(beginning_ap + vendor_expenses - accounts_payable, 0.0)

    tax = np.maximum(ebitda - depreciation, 0.0) * float(options["tax_rate"])
    change_ar = accounts_receivable - beginning_ar
    change_ap = accounts_payable - beginning_ap
    operating_cash_flow = ebitda - tax - change_ar + change_ap
    free_cash_flow = operating_cash_flow - capex
    starting_cash = float(options.get("opening_cash_eur", last_value(actuals, ("closing_cash_eur", "cash_eur"), 5_000_000.0)))
    closing_cash = starting_cash + np.cumsum(free_cash_flow)
    opening_cash = np.r_[starting_cash, closing_cash[:-1]]
    eur_ron = base_fx * (1.0 + fx_change) ** (step / 12.0)

    result = pd.DataFrame(
        {
            "month": dates,
            "period_type": "Forecast",
            "headcount": headcount,
            "revenue_headcount": revenue_headcount,
            "new_hires": new_hires,
            "incremental_hires": incremental_hires,
            "attrition": attrition,
            "billable_share": billable_share,
            "utilization": utilization,
            "working_days": working_days,
            "billing_rate_eur": billing_rate,
            "realization_rate": realization,
            "billable_capacity_hours": capacity_hours,
            "billable_hours": billable_hours,
            "model_baseline_revenue_eur": model_revenue,
            "management_adjustment_eur": management_adjustment,
            "management_adjustment_rationale": str(options["adjustment_rationale"]),
            "final_forecast_revenue_eur": revenue,
            "revenue_eur": revenue,
            "payroll_eur": payroll,
            "recruiting_cost_eur": recruiting_cost,
            "contractor_cost_eur": contractor_cost,
            "other_opex_eur": other_opex,
            "ebitda_eur": ebitda,
            "ebitda_margin": ebitda_margin,
            "depreciation_eur": depreciation,
            "tax_eur": tax,
            "capex_eur": capex,
            "dso": dso,
            "dpo": dpo,
            "accounts_receivable_eur": accounts_receivable,
            "accounts_payable_eur": accounts_payable,
            "cash_collections_eur": collections,
            "vendor_payments_eur": vendor_payments,
            "operating_cash_flow_eur": operating_cash_flow,
            "free_cash_flow_eur": free_cash_flow,
            "opening_cash_eur": opening_cash,
            "closing_cash_eur": closing_cash,
            "minimum_cash_threshold_eur": float(options["minimum_cash_threshold_eur"]),
            "liquidity_headroom_eur": closing_cash - float(options["minimum_cash_threshold_eur"]),
            "eur_ron": eur_ron,
        }
    )
    return result


# Descriptive alias for API consumers.
rolling_forecast = build_monthly_forecast
