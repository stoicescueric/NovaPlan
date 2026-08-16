"""Direct 13-week liquidity forecast."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ._utils import last_value, merge_options, monthly_values, recent_mean, sorted_monthly
from .working_capital import forecast_invoice_collections


DEFAULT_LIQUIDITY_ASSUMPTIONS: dict[str, Any] = {
    "weeks": 13,
    "minimum_cash_threshold_eur": 3_000_000.0,
    "collection_delay_days": 0,
    "collections_multiplier": 1.0,
    "payroll_multiplier": 1.0,
    "vendor_payments_multiplier": 1.0,
    "tax_payments_multiplier": 1.0,
    "capex_multiplier": 1.0,
    "other_payments_monthly_eur": 0.0,
    "use_invoice_schedule": True,
}


def _weekly_baseline(history: pd.DataFrame, names: tuple[str, ...], default: float) -> float:
    """Convert a recent average monthly amount to an average weekly amount."""

    return recent_mean(history, names, default, periods=3) * 12.0 / 52.0


def build_13_week_forecast(
    history: pd.DataFrame,
    invoices: pd.DataFrame | None = None,
    assumptions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build a direct weekly cash forecast from receipts and disbursements.

    Assumptions may contain scalar or weekly sequence overrides named
    ``weekly_collections_eur``, ``weekly_payroll_eur``,
    ``weekly_vendor_payments_eur``, ``weekly_tax_payments_eur``,
    ``weekly_capex_eur`` and ``weekly_other_payments_eur``.
    """

    options = merge_options(DEFAULT_LIQUIDITY_ASSUMPTIONS, assumptions)
    if assumptions and "minimum_cash_threshold" in assumptions and "minimum_cash_threshold_eur" not in assumptions:
        options["minimum_cash_threshold_eur"] = assumptions["minimum_cash_threshold"]
    clean = sorted_monthly(history)
    weeks = int(options.get("weeks", 13))
    if weeks <= 0:
        raise ValueError("weeks must be positive.")

    last_month = clean["month"].iloc[-1]
    default_start = last_month + pd.offsets.MonthEnd(0) + pd.Timedelta(days=1)
    start_date = pd.Timestamp(options.get("start_date", default_start)).normalize()
    start_date = start_date - pd.Timedelta(days=start_date.weekday())
    week_start = pd.date_range(start_date, periods=weeks, freq="W-MON")
    week_end = week_start + pd.Timedelta(days=6)

    opening_cash = float(
        options.get(
            "opening_cash_eur",
            last_value(clean, ("closing_cash_eur", "cash_eur"), 5_000_000.0),
        )
    )
    collections_base = _weekly_baseline(
        clean, ("cash_collections_eur", "collections_eur", "revenue_eur"), 1_500_000.0
    )
    payroll_base = _weekly_baseline(clean, ("payroll_eur",), 800_000.0)
    vendor_base = _weekly_baseline(
        clean, ("vendor_payments_eur", "vendor_expenses_eur"), 0.0
    )
    if vendor_base == 0.0:
        vendor_base = _weekly_baseline(clean, ("contractor_cost_eur",), 150_000.0)
        vendor_base += _weekly_baseline(clean, ("other_opex_eur",), 250_000.0)
    tax_base = _weekly_baseline(clean, ("tax_payments_eur", "tax_eur"), 0.0)
    if tax_base == 0.0:
        tax_base = max(_weekly_baseline(clean, ("ebitda_eur",), 250_000.0) * 0.16, 0.0)
    capex_base = _weekly_baseline(clean, ("capex_eur",), 35_000.0)
    other_base = float(options.get("other_payments_monthly_eur", 0.0)) * 12.0 / 52.0

    collections = monthly_values(options.get("weekly_collections_eur"), weeks, collections_base)
    if invoices is not None and bool(options.get("use_invoice_schedule", True)):
        baseline_invoice_schedule = forecast_invoice_collections(
            invoices,
            start_date,
            weeks,
            0,
        )
        invoice_schedule = forecast_invoice_collections(
            invoices,
            start_date,
            weeks,
            int(options.get("collection_delay_days", 0)),
        )
        baseline_values = baseline_invoice_schedule["invoice_collections_eur"].to_numpy(float)
        invoice_values = invoice_schedule["invoice_collections_eur"].to_numpy(float)
        # Weeks occupied by known invoices remain reserved even if a delay moves
        # their receipts elsewhere. This prevents a delayed receipt from being
        # silently replaced by the generic weekly baseline.
        known_invoice_week = (baseline_values > 0.0) | (invoice_values > 0.0)
        collections = np.where(known_invoice_week, invoice_values, collections)
        opening_cash += float(invoice_schedule.attrs.get("pre_start_collections_eur", 0.0))
    elif int(options.get("collection_delay_days", 0)):
        delay_weeks = int(np.sign(int(options["collection_delay_days"])) * np.ceil(abs(int(options["collection_delay_days"])) / 7.0))
        if delay_weeks > 0:
            collections = np.r_[np.zeros(delay_weeks), collections][:weeks]
        elif delay_weeks < 0:
            advance = -delay_weeks
            opening_cash += float(collections[:advance].sum())
            collections = np.r_[collections[advance:], np.zeros(advance)][:weeks]
    collections *= float(options.get("collections_multiplier", 1.0))

    payroll = monthly_values(options.get("weekly_payroll_eur"), weeks, payroll_base)
    vendor = monthly_values(options.get("weekly_vendor_payments_eur"), weeks, vendor_base)
    tax = monthly_values(options.get("weekly_tax_payments_eur"), weeks, tax_base)
    capex = monthly_values(options.get("weekly_capex_eur"), weeks, capex_base)
    other = monthly_values(options.get("weekly_other_payments_eur"), weeks, other_base)
    payroll *= float(options.get("payroll_multiplier", 1.0))
    vendor *= float(options.get("vendor_payments_multiplier", 1.0))
    tax *= float(options.get("tax_payments_multiplier", 1.0))
    capex *= float(options.get("capex_multiplier", 1.0))

    discretionary_change = float(options.get("discretionary_spending_change_pct", 0.0))
    if discretionary_change:
        discretionary_base = _weekly_baseline(clean, ("other_opex_eur",), 0.0)
        vendor = np.maximum(vendor + discretionary_base * discretionary_change, 0.0)

    incremental_hires = max(int(options.get("incremental_hires", 0)), 0)
    if incremental_hires:
        join_weeks = min(6, weeks)
        joins = np.zeros(weeks, dtype=int)
        joins[:join_weeks] = incremental_hires // join_weeks
        joins[: incremental_hires % join_weeks] += 1
        active_hires = np.cumsum(joins)
        payroll_per_fte_monthly = recent_mean(
            clean.assign(
                _payroll_per_fte=pd.to_numeric(clean.get("payroll_eur", pd.Series(index=clean.index, dtype=float)), errors="coerce")
                / pd.to_numeric(clean.get("headcount", pd.Series(index=clean.index, dtype=float)), errors="coerce").replace(0, np.nan)
            ),
            ("_payroll_per_fte",),
            3_500.0,
            periods=3,
        )
        payroll += active_hires * payroll_per_fte_monthly * 12.0 / 52.0
        other += joins * float(options.get("recruiting_cost_per_hire_eur", 3_000.0))
        capex += joins * float(options.get("equipment_cost_per_hire_eur", 1_800.0))

    capex_shift = int(options.get("capex_timing_shift_weeks", 0))
    if capex_shift > 0:
        capex = np.r_[np.zeros(capex_shift), capex][:weeks]
    elif capex_shift < 0:
        capex = np.r_[capex[-capex_shift:], np.zeros(-capex_shift)][:weeks]

    large_payment = float(options.get("large_customer_payment_eur", 0.0))
    if large_payment:
        payment_week = int(options.get("large_customer_payment_week", 1)) - 1
        if 0 <= payment_week < weeks:
            collections[payment_week] += large_payment
    collections = np.maximum(collections, 0.0)

    total_disbursements = payroll + vendor + tax + capex + other
    net_cash_flow = collections - total_disbursements
    closing_cash = opening_cash + np.cumsum(net_cash_flow)
    weekly_opening = np.r_[opening_cash, closing_cash[:-1]]
    threshold = float(options.get("minimum_cash_threshold_eur", 3_000_000.0))

    result = pd.DataFrame(
        {
            "week": week_start,
            "week_number": np.arange(1, weeks + 1),
            "week_start": week_start,
            "week_end": week_end,
            "opening_cash_eur": weekly_opening,
            "customer_collections_eur": collections,
            "payroll_eur": payroll,
            "vendor_payments_eur": vendor,
            "tax_payments_eur": tax,
            "capex_eur": capex,
            "other_scheduled_payments_eur": other,
            "total_disbursements_eur": total_disbursements,
            "net_cash_flow_eur": net_cash_flow,
            "closing_cash_eur": closing_cash,
            "minimum_cash_threshold_eur": threshold,
            "liquidity_headroom_eur": closing_cash - threshold,
            "funding_requirement_eur": np.maximum(threshold - closing_cash, 0.0),
            "below_minimum_cash": closing_cash < threshold,
        }
    )
    result["is_lowest_cash_week"] = result["closing_cash_eur"].eq(result["closing_cash_eur"].min())
    return result


# Concise alias used by some page modules.
build_liquidity_forecast = build_13_week_forecast
