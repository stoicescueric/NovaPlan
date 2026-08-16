"""Working-capital timing and reconciliation tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.working_capital import build_working_capital, calculate_ar


def _monthly_inputs() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": pd.date_range("2026-01-01", periods=4, freq="MS"),
            "revenue_eur": [1_000_000.0] * 4,
            "contractor_cost_eur": [100_000.0] * 4,
            "other_opex_eur": [150_000.0] * 4,
        }
    )


def test_higher_dso_increases_ar_and_reduces_near_term_collections() -> None:
    assumptions = {
        "opening_ar_eur": 1_500_000.0,
        "writeoff_rate": 0.0,
        "respect_reported_balances": False,
    }
    base = build_working_capital(
        _monthly_inputs().assign(dso=45),
        assumptions=assumptions,
    )
    delayed = build_working_capital(
        _monthly_inputs().assign(dso=65),
        assumptions=assumptions,
    )

    # Revenue recognition is unchanged: DSO only changes collection timing.
    np.testing.assert_allclose(delayed["revenue_eur"], base["revenue_eur"])
    assert delayed.loc[0, "accounts_receivable_eur"] > base.loc[0, "accounts_receivable_eur"]
    assert delayed.loc[0, "cash_collections_eur"] < base.loc[0, "cash_collections_eur"]
    assert calculate_ar(1_000_000, 65) > calculate_ar(1_000_000, 45)


def test_ar_and_ap_schedules_reconcile() -> None:
    schedule = build_working_capital(
        _monthly_inputs().assign(dso=[50, 55, 60, 52], dpo=[30, 35, 38, 34]),
        assumptions={
            "opening_ar_eur": 1_600_000.0,
            "opening_ap_eur": 300_000.0,
            "writeoff_rate": 0.001,
            "respect_reported_balances": False,
        },
    )

    ending_ar = (
        schedule["beginning_ar_eur"]
        + schedule["invoices_eur"]
        - schedule["cash_collections_eur"]
        - schedule["writeoffs_eur"]
    )
    ending_ap = (
        schedule["beginning_ap_eur"]
        + schedule["vendor_expenses_eur"]
        - schedule["vendor_payments_eur"]
    )
    np.testing.assert_allclose(schedule["accounts_receivable_eur"], ending_ar)
    np.testing.assert_allclose(schedule["accounts_payable_eur"], ending_ap)
    assert (schedule["cash_collections_eur"] >= 0).all()
    assert (schedule["vendor_payments_eur"] >= 0).all()
