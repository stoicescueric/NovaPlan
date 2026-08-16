"""Workforce roll-forward and proposed-hire economics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from ._utils import first_existing, merge_options, recent_mean, sorted_monthly


@dataclass(frozen=True, slots=True)
class HireProposal:
    """Illustrative financial assumptions for one proposed employee.

    ``proposed_base_salary_eur`` and ``benefits_eur`` are annual amounts. The
    compensation outputs support planning; they are not legal or market advice.
    """

    role: str = "Consultant"
    seniority: str = "Mid"
    proposed_base_salary_eur: float = 42_000.0
    joining_month: str | pd.Timestamp | None = None
    expected_billing_rate_eur: float = 72.0
    expected_utilization: float = 0.74
    ramp_up_months: int = 3
    employer_oncost_rate: float = 0.08
    bonus_percent: float = 0.08
    benefits_eur: float = 2_400.0
    recruiting_cost_eur: float = 3_000.0
    equipment_cost_eur: float = 1_800.0
    realization_rate: float = 0.97
    available_working_days: float = 220.0
    hours_per_day: float = 8.0

    def __post_init__(self) -> None:
        non_negative = (
            "proposed_base_salary_eur",
            "expected_billing_rate_eur",
            "benefits_eur",
            "recruiting_cost_eur",
            "equipment_cost_eur",
        )
        if any(getattr(self, field) < 0 for field in non_negative):
            raise ValueError("Salary, rates, benefits and one-off costs cannot be negative.")
        if not 0 <= self.expected_utilization <= 1.0:
            raise ValueError("expected_utilization must be between 0 and 1.")
        if not 0 <= self.realization_rate <= 1.1:
            raise ValueError("realization_rate must be between 0 and 1.1.")
        if self.ramp_up_months < 0:
            raise ValueError("ramp_up_months cannot be negative.")


def workforce_rollforward(
    beginning_headcount: float,
    hires: float,
    attrition: float,
) -> float:
    """Calculate ending headcount, bounded at zero."""

    if min(beginning_headcount, hires, attrition) < 0:
        raise ValueError("Headcount, hires and attrition cannot be negative.")
    return float(max(beginning_headcount + hires - attrition, 0.0))


def _ramp_factors(months: int, ramp_up_months: int) -> np.ndarray:
    if ramp_up_months <= 0:
        return np.ones(months)
    index = np.arange(1, months + 1, dtype=float)
    return np.minimum(index / ramp_up_months, 1.0)


def compensation_band(
    employees: pd.DataFrame | None,
    seniority: str,
    proposed_salary_eur: float,
) -> dict[str, Any]:
    """Create an internal, placeholder-market and analytical planning range."""

    default_low = proposed_salary_eur * 0.85
    default_high = proposed_salary_eur * 1.15
    internal_low, internal_high, peer_count = default_low, default_high, 0

    if employees is not None and not employees.empty:
        salary_column = first_existing(
            employees,
            (
                "annual_base_salary_eur",
                "base_salary_eur_annual",
                "base_salary_eur",
                "salary_eur",
                "monthly_base_salary_eur",
                "base_salary_eur_monthly",
            ),
        )
        level_column = first_existing(employees, ("seniority", "level", "grade"))
        peers = employees
        if level_column:
            match = employees[level_column].astype(str).str.casefold() == seniority.casefold()
            if match.any():
                peers = employees.loc[match]
        if salary_column and not peers.empty:
            salaries = pd.to_numeric(peers[salary_column], errors="coerce").dropna()
            if "monthly" in salary_column:
                salaries = salaries * 12.0
            # A generic ``base_salary_eur`` below EUR 15k is likely monthly.
            if salary_column in {"base_salary_eur", "salary_eur"} and salaries.median() < 15_000:
                salaries = salaries * 12.0
            if not salaries.empty:
                internal_low = float(salaries.quantile(0.25))
                internal_high = float(salaries.quantile(0.75))
                peer_count = int(len(salaries))

    midpoint = (internal_low + internal_high) / 2.0
    market_low, market_high = midpoint * 0.90, midpoint * 1.15
    recommended_low = max(internal_low, market_low)
    recommended_high = min(internal_high, market_high)
    if recommended_low > recommended_high:
        recommended_low, recommended_high = internal_low, internal_high

    if proposed_salary_eur < internal_low:
        position = "Below internal range"
        equity_risk = "Potential retention or offer-acceptance risk"
    elif proposed_salary_eur > internal_high:
        position = "Above internal range"
        equity_risk = "Potential internal-equity risk"
    else:
        position = "Within internal range"
        equity_risk = "No material range exception"

    return {
        "internal_salary_low_eur": float(internal_low),
        "internal_salary_high_eur": float(internal_high),
        "market_placeholder_low_eur": float(market_low),
        "market_placeholder_high_eur": float(market_high),
        "recommended_analytical_low_eur": float(recommended_low),
        "recommended_analytical_high_eur": float(recommended_high),
        "salary_position": position,
        "internal_equity_flag": equity_risk,
        "internal_peer_count": peer_count,
        "compensation_note": "Illustrative compensation planning support, not a salary determination.",
    }


def evaluate_hire(
    proposal: HireProposal | None = None,
    *,
    role: str = "Consultant",
    seniority: str = "Mid",
    proposed_base_salary_eur: float = 42_000.0,
    joining_month: str | pd.Timestamp | None = None,
    expected_billing_rate_eur: float = 72.0,
    expected_utilization: float = 0.74,
    ramp_up_months: int = 3,
    employer_oncost_rate: float = 0.08,
    bonus_percent: float = 0.08,
    benefits_eur: float = 2_400.0,
    recruiting_cost_eur: float = 3_000.0,
    equipment_cost_eur: float = 1_800.0,
    realization_rate: float = 0.97,
    available_working_days: float = 220.0,
    hours_per_day: float = 8.0,
    internal_salary_data: pd.DataFrame | None = None,
    base_salary_eur: float | None = None,
    billing_rate_eur: float | None = None,
    utilization: float | None = None,
) -> dict[str, Any]:
    """Evaluate the 12-month economics and cash profile of a proposed hire.

    The three short alias parameters make the function convenient for UI forms.
    Equipment is treated as capex: it reduces cash but not EBITDA immediately.
    """

    if proposal is None:
        proposal = HireProposal(
            role=role,
            seniority=seniority,
            proposed_base_salary_eur=(base_salary_eur if base_salary_eur is not None else proposed_base_salary_eur),
            joining_month=joining_month,
            expected_billing_rate_eur=(billing_rate_eur if billing_rate_eur is not None else expected_billing_rate_eur),
            expected_utilization=(utilization if utilization is not None else expected_utilization),
            ramp_up_months=ramp_up_months,
            employer_oncost_rate=employer_oncost_rate,
            bonus_percent=bonus_percent,
            benefits_eur=benefits_eur,
            recruiting_cost_eur=recruiting_cost_eur,
            equipment_cost_eur=equipment_cost_eur,
            realization_rate=realization_rate,
            available_working_days=available_working_days,
            hours_per_day=hours_per_day,
        )

    annual_salary_load = proposal.proposed_base_salary_eur * (
        1.0 + proposal.employer_oncost_rate + proposal.bonus_percent
    )
    recurring_cost = annual_salary_load + proposal.benefits_eur
    annual_hours = proposal.available_working_days * proposal.hours_per_day
    steady_annual_revenue = (
        annual_hours
        * proposal.expected_billing_rate_eur
        * proposal.expected_utilization
        * proposal.realization_rate
    )
    ramp = _ramp_factors(12, proposal.ramp_up_months)
    monthly_revenue = steady_annual_revenue / 12.0 * ramp
    expected_revenue = float(monthly_revenue.sum())
    contribution = expected_revenue - recurring_cost
    ebitda_effect = contribution - proposal.recruiting_cost_eur
    year_one_cash_cost = recurring_cost + proposal.recruiting_cost_eur + proposal.equipment_cost_eur
    cash_effect = expected_revenue - year_one_cash_cost
    break_even_utilization = (
        recurring_cost
        / (proposal.expected_billing_rate_eur * annual_hours * proposal.realization_rate)
        if proposal.expected_billing_rate_eur * annual_hours * proposal.realization_rate > 0
        else np.inf
    )

    payback_ramp = _ramp_factors(36, proposal.ramp_up_months)
    monthly_cash = steady_annual_revenue / 12.0 * payback_ramp - recurring_cost / 12.0
    monthly_cash[0] -= proposal.recruiting_cost_eur + proposal.equipment_cost_eur
    cumulative = np.cumsum(monthly_cash)
    paid_back = np.flatnonzero(cumulative >= 0)
    payback_months: int | None = int(paid_back[0] + 1) if paid_back.size else None

    result: dict[str, Any] = {
        "role": proposal.role,
        "seniority": proposal.seniority,
        "joining_month": None if proposal.joining_month is None else str(pd.Timestamp(proposal.joining_month).date()),
        "proposed_base_salary_eur": proposal.proposed_base_salary_eur,
        "total_annual_employer_cost_eur": float(recurring_cost),
        "year_1_cash_cost_eur": float(year_one_cash_cost),
        "steady_state_annual_revenue_eur": float(steady_annual_revenue),
        "expected_billable_revenue_eur": expected_revenue,
        "expected_contribution_margin_eur": float(contribution),
        "contribution_margin_percent": float(contribution / expected_revenue) if expected_revenue else 0.0,
        "break_even_utilization": float(break_even_utilization),
        "expected_payback_period_months": payback_months,
        "ebitda_effect_eur": float(ebitda_effect),
        "cash_effect_12m_eur": float(cash_effect),
        "financially_viable": bool(contribution > 0 and break_even_utilization <= proposal.expected_utilization),
        "ramp_factors": ramp.tolist(),
        "assumptions": asdict(proposal),
    }
    result.update(compensation_band(internal_salary_data, proposal.seniority, proposal.proposed_base_salary_eur))
    return result


def simulate_hiring_plan(
    history: pd.DataFrame | None = None,
    hires: int = 40,
    months: int = 18,
    assumptions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Simulate monthly incremental economics for a staggered hiring cohort."""

    if hires < 0 or months <= 0:
        raise ValueError("hires must be non-negative and months must be positive.")
    options = merge_options(
        {
            "joining_months": 6,
            "ramp_up_months": 3,
            "annual_employer_cost_eur": None,
            "annual_base_salary_eur": 42_000.0,
            "employer_oncost_rate": 0.08,
            "bonus_percent": 0.08,
            "benefits_eur": 2_400.0,
            "billing_rate_eur": 72.0,
            "utilization": 0.74,
            "realization_rate": 0.97,
            "hours_per_day": 8.0,
            "working_days": 21.0,
            "recruiting_cost_eur": 3_000.0,
            "equipment_cost_eur": 1_800.0,
            "start_month": None,
        },
        assumptions,
    )

    if history is not None and not history.empty:
        clean = sorted_monthly(history)
        start = clean["month"].iloc[-1] + pd.offsets.MonthBegin(1)
        monthly_cost_per_fte = recent_mean(clean.assign(
            _cost_per_fte=pd.to_numeric(clean.get("payroll_eur", pd.Series(index=clean.index, dtype=float)), errors="coerce")
            / pd.to_numeric(clean.get("headcount", pd.Series(index=clean.index, dtype=float)), errors="coerce").replace(0, np.nan)
        ), ("_cost_per_fte",), 0.0)
        if options["annual_employer_cost_eur"] is None and monthly_cost_per_fte > 0:
            options["annual_employer_cost_eur"] = monthly_cost_per_fte * 12.0
    else:
        start = pd.Timestamp(options["start_month"] or "2026-01-01").to_period("M").to_timestamp()

    if options["start_month"] is not None:
        start = pd.Timestamp(options["start_month"]).to_period("M").to_timestamp()
    annual_cost = options["annual_employer_cost_eur"]
    if annual_cost is None:
        annual_cost = float(options["annual_base_salary_eur"]) * (
            1.0 + float(options["employer_oncost_rate"]) + float(options["bonus_percent"])
        ) + float(options["benefits_eur"])

    joining_months = max(1, min(int(options["joining_months"]), months))
    joins = np.zeros(months, dtype=int)
    if hires:
        joins[:joining_months] = hires // joining_months
        joins[: hires % joining_months] += 1

    active = np.cumsum(joins)
    ramped_fte = np.zeros(months)
    for cohort_month, cohort_size in enumerate(joins):
        if cohort_size == 0:
            continue
        cohort_horizon = months - cohort_month
        ramped_fte[cohort_month:] += cohort_size * _ramp_factors(
            cohort_horizon, int(options["ramp_up_months"])
        )

    revenue_per_productive_fte = (
        float(options["working_days"])
        * float(options["hours_per_day"])
        * float(options["billing_rate_eur"])
        * float(options["utilization"])
        * float(options["realization_rate"])
    )
    revenue = ramped_fte * revenue_per_productive_fte
    payroll = active * float(annual_cost) / 12.0
    recruiting = joins * float(options["recruiting_cost_eur"])
    equipment = joins * float(options["equipment_cost_eur"])
    ebitda = revenue - payroll - recruiting
    cash = ebitda - equipment

    return pd.DataFrame(
        {
            "month": pd.date_range(start, periods=months, freq="MS"),
            "new_hires": joins,
            "incremental_headcount": active,
            "ramped_billable_fte": ramped_fte,
            "incremental_revenue_eur": revenue,
            "incremental_payroll_eur": payroll,
            "recruiting_cost_eur": recruiting,
            "onboarding_capex_eur": equipment,
            "incremental_ebitda_eur": ebitda,
            "incremental_cash_effect_eur": cash,
            "cumulative_cash_effect_eur": np.cumsum(cash),
        }
    )


# Backwards-friendly name for UI code.
proposed_hire_economics = evaluate_hire
