"""Determinism, completeness, causality, and realism checks for demo data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from synthetic.generate_company import generate_company


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pd.DataFrame]:
    output = tmp_path_factory.mktemp("novaplan_data")
    return generate_company(output_dir=output, seed=42, write_parquet=False)


def test_generator_creates_all_required_datasets(generated: dict[str, pd.DataFrame]) -> None:
    assert set(generated) == {
        "monthly_kpis",
        "invoices",
        "customers",
        "employees",
        "hiring_plan",
        "opex",
        "capex",
        "weekly_cash_actuals",
    }
    assert all(not frame.empty for frame in generated.values())


def test_generator_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    first = generate_company(tmp_path / "first", seed=42, write_parquet=False)
    second = generate_company(tmp_path / "second", seed=42, write_parquet=False)

    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_monthly_history_has_required_columns_and_plausible_ranges(
    generated: dict[str, pd.DataFrame],
) -> None:
    monthly = generated["monthly_kpis"]
    required = {
        "month",
        "headcount",
        "new_hires",
        "attrition",
        "billable_share",
        "utilization",
        "working_days",
        "billing_rate_eur",
        "realization_rate",
        "backlog_eur",
        "revenue_eur",
        "payroll_eur",
        "contractor_cost_eur",
        "other_opex_eur",
        "ebitda_eur",
        "ebitda_margin",
        "capex_eur",
        "accounts_receivable_eur",
        "accounts_payable_eur",
        "dso",
        "dpo",
        "cash_collections_eur",
        "operating_cash_flow_eur",
        "free_cash_flow_eur",
        "closing_cash_eur",
        "eur_ron",
    }
    assert len(monthly) == 72
    assert required.issubset(monthly.columns)
    assert pd.to_datetime(monthly["month"]).min() == pd.Timestamp("2020-01-01")
    assert pd.to_datetime(monthly["month"]).max() == pd.Timestamp("2025-12-01")
    assert monthly["utilization"].between(0.55, 0.90).all()
    assert monthly["billable_share"].between(0.70, 0.90).all()
    assert monthly["dso"].between(30, 90).all()
    assert (monthly["billing_rate_eur"] > 0).all()
    assert (monthly["headcount"] > 0).all()
    assert (monthly["cash_collections_eur"] >= 0).all()


def test_monthly_rollforwards_preserve_business_causality(
    generated: dict[str, pd.DataFrame],
) -> None:
    monthly = generated["monthly_kpis"]
    np.testing.assert_allclose(
        monthly["headcount"],
        monthly["beginning_headcount"] + monthly["new_hires"] - monthly["attrition"],
    )
    np.testing.assert_allclose(
        monthly["accounts_receivable_eur"],
        monthly["beginning_ar_eur"]
        + monthly["revenue_eur"]
        - monthly["cash_collections_eur"]
        - monthly["writeoffs_eur"],
        atol=0.01,
    )
    np.testing.assert_allclose(
        monthly["closing_cash_eur"],
        monthly["opening_cash_eur"] + monthly["net_change_in_cash_eur"],
        atol=0.01,
    )


def test_seasonality_stress_and_non_smoothness_are_visible(
    generated: dict[str, pd.DataFrame],
) -> None:
    monthly = generated["monthly_kpis"].copy()
    monthly["month_number"] = pd.to_datetime(monthly["month"]).dt.month
    by_month = monthly.groupby("month_number")["utilization"].mean()

    core_months = by_month.loc[[1, 2, 3, 4, 5, 6, 9, 10, 11]].mean()
    assert by_month.loc[[7, 8]].mean() < core_months
    assert by_month.loc[12] < core_months
    assert monthly["dso"].max() >= 65
    assert monthly["utilization"].std() > 0.02
    assert monthly["revenue_eur"].pct_change().std() > 0.02
    # EUR/RON moves, but not as independent month-to-month jumps.
    assert monthly["eur_ron"].diff().dropna().abs().max() < 0.15


def test_invoice_and_customer_data_are_consistent_and_concentrated(
    generated: dict[str, pd.DataFrame],
) -> None:
    invoices = generated["invoices"]
    customers = generated["customers"]
    required_invoice_columns = {
        "invoice_id",
        "customer_id",
        "invoice_date",
        "amount_eur",
        "payment_terms_days",
        "expected_payment_date",
        "actual_payment_date",
        "days_late",
        "status",
        "service_line",
    }
    assert required_invoice_columns.issubset(invoices.columns)
    assert invoices["invoice_id"].is_unique
    assert invoices["customer_id"].isin(customers["customer_id"]).all()
    assert (invoices["amount_eur"] > 0).all()

    concentration = (
        invoices.groupby("customer_id")["amount_eur"].sum().nlargest(5).sum()
        / invoices["amount_eur"].sum()
    )
    assert 0.35 <= concentration <= 0.80


def test_employee_and_expansion_plan_have_economic_fields(
    generated: dict[str, pd.DataFrame],
) -> None:
    employees = generated["employees"]
    plan = generated["hiring_plan"]
    assert {"Junior", "Mid", "Senior"}.issubset(set(employees["seniority"]))
    assert {"annual_base_salary_eur", "employer_oncost_rate", "bonus_percent"}.issubset(
        employees.columns
    )
    assert (employees["annual_base_salary_eur"] > 0).all()
    expansion = plan.loc[plan["scenario"].eq("2026 Expansion Decision")]
    assert expansion["planned_hires"].sum() == 40
    assert (expansion["ramp_up_months"] > 0).all()
