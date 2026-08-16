"""Rolling forecast management-driver tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.forecast import build_monthly_forecast
from models.scenarios import scenario_assumptions


def _history() -> pd.DataFrame:
    periods = 24
    position = np.arange(periods)
    frame = pd.DataFrame(
        {
            "month": pd.date_range("2024-01-01", periods=periods, freq="MS"),
            "headcount": 280 + position * 0.5,
            "new_hires": [3.0] * periods,
            "attrition": [2.0] * periods,
            "billable_share": [0.82] * periods,
            "utilization": 0.74 + 0.025 * np.sin(position * 2 * np.pi / 12),
            "working_days": [21] * periods,
            "billing_rate_eur": 62 + position * 0.08,
            "realization_rate": [0.97] * periods,
            "payroll_eur": [850_000.0] * periods,
            "contractor_cost_eur": [130_000.0] * periods,
            "other_opex_eur": [250_000.0] * periods,
            "capex_eur": [35_000.0] * periods,
            "dso": [55.0] * periods,
            "dpo": [35.0] * periods,
            "accounts_receivable_eur": [2_500_000.0] * periods,
            "accounts_payable_eur": [450_000.0] * periods,
            "closing_cash_eur": [5_500_000.0] * periods,
            "eur_ron": [4.97] * periods,
        }
    )
    frame["revenue_eur"] = (
        frame["headcount"]
        * frame["billable_share"]
        * frame["working_days"]
        * 8
        * frame["utilization"]
        * frame["billing_rate_eur"]
        * frame["realization_rate"]
    )
    return frame


def test_forecast_separates_model_adjustment_and_final() -> None:
    forecast = build_monthly_forecast(
        _history(),
        months=6,
        overrides={
            "management_revenue_adjustment_eur": 100_000,
            "adjustment_rationale": "Signed scope extension",
        },
    )

    np.testing.assert_allclose(
        forecast["final_forecast_revenue_eur"],
        forecast["model_baseline_revenue_eur"] + forecast["management_adjustment_eur"],
    )
    assert (forecast["management_adjustment_eur"] == 100_000).all()
    assert (forecast["management_adjustment_rationale"] == "Signed scope extension").all()


def test_higher_dso_reduces_cash_but_not_forecast_revenue() -> None:
    base = build_monthly_forecast(_history(), months=6, overrides={"dso_days": 50})
    delayed = build_monthly_forecast(_history(), months=6, overrides={"dso_days": 70})

    np.testing.assert_allclose(delayed["revenue_eur"], base["revenue_eur"])
    assert delayed["accounts_receivable_eur"].iloc[0] > base["accounts_receivable_eur"].iloc[0]
    assert delayed["closing_cash_eur"].iloc[0] < base["closing_cash_eur"].iloc[0]


def test_capex_reduces_cash_without_reducing_ebitda() -> None:
    base = build_monthly_forecast(_history(), months=6, overrides={"capex_change_pct": 0})
    higher_capex = build_monthly_forecast(
        _history(), months=6, overrides={"capex_change_pct": 0.50}
    )

    np.testing.assert_allclose(higher_capex["ebitda_eur"], base["ebitda_eur"])
    assert higher_capex["closing_cash_eur"].iloc[-1] < base["closing_cash_eur"].iloc[-1]


def test_incremental_hiring_staggers_joining_and_ramps_revenue_headcount() -> None:
    base = build_monthly_forecast(_history(), months=9)
    expansion = build_monthly_forecast(
        _history(),
        months=9,
        overrides={
            "incremental_hires_total": 12,
            "hire_joining_months": 3,
            "hire_ramp_months": 3,
        },
    )

    assert expansion["incremental_hires"].sum() == pytest.approx(12)
    assert (expansion["incremental_hires"].iloc[:3] > 0).all()
    assert (expansion["incremental_hires"].iloc[3:] == 0).all()
    headcount_uplift = expansion["headcount"] - base["headcount"]
    revenue_headcount_uplift = expansion["revenue_headcount"] - base["revenue_headcount"]
    assert revenue_headcount_uplift.iloc[0] < headcount_uplift.iloc[0]
    assert revenue_headcount_uplift.iloc[5] > revenue_headcount_uplift.iloc[0]


def test_scenario_lab_changes_are_added_to_the_selected_preset() -> None:
    assumptions = scenario_assumptions(
        "Hiring Expansion",
        {
            "_delta_mode": True,
            "incremental_hires": 5,
            "billing_rate_change_pct": 0.01,
            "dso_delta_days": 2,
        },
    )

    assert assumptions["incremental_hires_total"] == pytest.approx(45)
    assert assumptions["billing_rate_change_pct"] == pytest.approx(0.01)
    assert assumptions["dso_delta_days"] == pytest.approx(2)


def test_zero_scenario_lab_delta_preserves_the_preset() -> None:
    assumptions = scenario_assumptions(
        "Pricing Initiative",
        {
            "_delta_mode": True,
            "revenue_demand_change_pct": 0.0,
            "utilization_delta_pp": 0.0,
            "billing_rate_change_pct": 0.0,
            "incremental_hires": 0,
        },
    )

    assert assumptions["billing_rate_change_pct"] == pytest.approx(0.05)
    assert assumptions["utilization_change_pp"] == pytest.approx(-0.01)
