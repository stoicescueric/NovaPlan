"""Direct-liquidity forecast tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.cashflow import build_13_week_forecast


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": pd.date_range("2025-07-01", periods=6, freq="MS"),
            "revenue_eur": [1_500_000.0] * 6,
            "cash_collections_eur": [1_450_000.0] * 6,
            "payroll_eur": [760_000.0] * 6,
            "contractor_cost_eur": [160_000.0] * 6,
            "other_opex_eur": [260_000.0] * 6,
            "ebitda_eur": [320_000.0] * 6,
            "capex_eur": [35_000.0] * 6,
            "closing_cash_eur": [5_000_000.0] * 6,
        }
    )


def _explicit_assumptions() -> dict:
    return {
        "opening_cash_eur": 5_000_000.0,
        "weekly_collections_eur": 350_000.0,
        "weekly_payroll_eur": 180_000.0,
        "weekly_vendor_payments_eur": 95_000.0,
        "weekly_tax_payments_eur": 12_000.0,
        "weekly_capex_eur": 8_000.0,
        "weekly_other_payments_eur": 5_000.0,
        "use_invoice_schedule": False,
    }


def test_direct_cash_forecast_rolls_forward_and_reports_headroom() -> None:
    forecast = build_13_week_forecast(_history(), assumptions=_explicit_assumptions())

    assert len(forecast) == 13
    np.testing.assert_allclose(
        forecast["closing_cash_eur"],
        forecast["opening_cash_eur"] + forecast["net_cash_flow_eur"],
    )
    np.testing.assert_allclose(
        forecast["liquidity_headroom_eur"],
        forecast["closing_cash_eur"] - forecast["minimum_cash_threshold_eur"],
    )
    np.testing.assert_allclose(
        forecast["funding_requirement_eur"],
        np.maximum(-forecast["liquidity_headroom_eur"], 0.0),
    )
    assert forecast["is_lowest_cash_week"].sum() == 1


def test_collection_delay_reduces_near_term_cash_without_changing_history() -> None:
    base = build_13_week_forecast(_history(), assumptions=_explicit_assumptions())
    delayed = build_13_week_forecast(
        _history(),
        assumptions={**_explicit_assumptions(), "collection_delay_days": 14},
    )

    assert delayed.loc[0, "customer_collections_eur"] == 0
    assert delayed.loc[1, "customer_collections_eur"] == 0
    assert delayed.loc[1, "closing_cash_eur"] < base.loc[1, "closing_cash_eur"]


def test_invoice_delays_are_monotonic_and_not_backfilled_at_the_horizon_edge() -> None:
    invoice_dates = pd.date_range("2026-01-05", periods=13, freq="W-MON")
    invoices = pd.DataFrame(
        {
            "amount_eur": [350_000.0] * 13,
            "expected_payment_date": invoice_dates,
            "actual_payment_date": [pd.NaT] * 13,
            "status": ["open"] * 13,
        }
    )
    common = {**_explicit_assumptions(), "start_date": "2026-01-05", "use_invoice_schedule": True}

    base = build_13_week_forecast(_history(), invoices, common)
    delay_14 = build_13_week_forecast(
        _history(), invoices, {**common, "collection_delay_days": 14}
    )
    delay_28 = build_13_week_forecast(
        _history(), invoices, {**common, "collection_delay_days": 28}
    )

    assert base["closing_cash_eur"].iloc[-1] > delay_14["closing_cash_eur"].iloc[-1]
    assert delay_14["closing_cash_eur"].iloc[-1] > delay_28["closing_cash_eur"].iloc[-1]


def test_accelerated_invoice_receipts_are_carried_into_opening_cash() -> None:
    invoice_dates = pd.date_range("2026-01-05", periods=13, freq="W-MON")
    invoices = pd.DataFrame(
        {
            "amount_eur": [350_000.0] * 13,
            "expected_payment_date": invoice_dates,
            "actual_payment_date": [pd.NaT] * 13,
            "status": ["open"] * 13,
        }
    )
    common = {**_explicit_assumptions(), "start_date": "2026-01-05", "use_invoice_schedule": True}
    base = build_13_week_forecast(_history(), invoices, common)
    accelerated = build_13_week_forecast(
        _history(), invoices, {**common, "collection_delay_days": -14}
    )

    assert accelerated["opening_cash_eur"].iloc[0] > base["opening_cash_eur"].iloc[0]
    assert accelerated["closing_cash_eur"].iloc[-1] == pytest.approx(
        base["closing_cash_eur"].iloc[-1]
    )
