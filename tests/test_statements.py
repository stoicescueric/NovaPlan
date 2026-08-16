"""Integrated statement and cash-roll-forward tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.statements import build_statements, check_reconciliation


def _statement_inputs(capex_eur: float = 40_000.0, payroll_eur: float = 500_000.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": pd.date_range("2026-01-01", periods=6, freq="MS"),
            "revenue_eur": [1_100_000.0] * 6,
            "payroll_eur": [payroll_eur] * 6,
            "contractor_cost_eur": [120_000.0] * 6,
            "other_opex_eur": [180_000.0] * 6,
            "capex_eur": [capex_eur] * 6,
            "dso": [55.0] * 6,
            "dpo": [35.0] * 6,
        }
    )


def test_statements_and_cash_rollforward_reconcile_each_month() -> None:
    statements = build_statements(_statement_inputs())
    check = check_reconciliation(statements)

    assert check["is_reconciled"]
    assert check["failed_periods"] == 0
    balance = statements["balance_sheet"]
    cash_flow = statements["cash_flow"]
    np.testing.assert_allclose(
        balance["total_assets_eur"],
        balance["total_liabilities_and_equity_eur"],
        atol=1.0,
    )
    np.testing.assert_allclose(
        cash_flow["closing_cash_eur"],
        cash_flow["opening_cash_eur"] + cash_flow["net_change_in_cash_eur"],
        atol=1e-8,
    )


def test_capex_reduces_cash_but_not_ebitda() -> None:
    without_capex = build_statements(_statement_inputs(capex_eur=0.0))
    with_capex = build_statements(_statement_inputs(capex_eur=100_000.0))

    np.testing.assert_allclose(
        with_capex["income_statement"]["ebitda_eur"],
        without_capex["income_statement"]["ebitda_eur"],
    )
    first_month_cash_delta = (
        with_capex["cash_flow"].loc[0, "closing_cash_eur"]
        - without_capex["cash_flow"].loc[0, "closing_cash_eur"]
    )
    assert first_month_cash_delta == pytest.approx(-100_000.0)
    assert with_capex["cash_flow"].loc[0, "investing_cash_flow_eur"] == -100_000.0


def test_higher_payroll_reduces_ebitda_and_cash() -> None:
    base = build_statements(_statement_inputs(payroll_eur=500_000.0))
    higher_salary = build_statements(_statement_inputs(payroll_eur=560_000.0))

    assert higher_salary["income_statement"].loc[0, "ebitda_eur"] < base["income_statement"].loc[0, "ebitda_eur"]
    assert higher_salary["cash_flow"].loc[0, "closing_cash_eur"] < base["cash_flow"].loc[0, "closing_cash_eur"]


def test_reconciliation_summary_flags_a_material_difference() -> None:
    checks = build_statements(_statement_inputs())["checks"].copy()
    checks.loc[2, "balance_difference_eur"] = 10.0

    result = check_reconciliation(checks, tolerance_eur=1.0)

    assert not result["is_reconciled"]
    assert result["failed_periods"] == 1
