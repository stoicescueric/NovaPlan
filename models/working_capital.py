"""Accounts receivable, accounts payable and invoice collection logic."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ._utils import first_existing, merge_options, monthly_values, sorted_monthly


AVERAGE_DAYS_PER_MONTH = 365.25 / 12.0


@dataclass(frozen=True, slots=True)
class WorkingCapitalAssumptions:
    """Illustrative working-capital assumptions."""

    dso_days: float = 55.0
    dpo_days: float = 35.0
    writeoff_rate: float = 0.001
    other_current_assets_percent_revenue: float = 0.02


def calculate_ar(revenue_eur: Any, dso_days: Any, days_in_month: float = AVERAGE_DAYS_PER_MONTH) -> Any:
    """Estimate ending accounts receivable from revenue and DSO."""

    result = np.asarray(revenue_eur, dtype=float) * np.asarray(dso_days, dtype=float) / days_in_month
    return float(result) if result.ndim == 0 else result


def calculate_ap(vendor_expenses_eur: Any, dpo_days: Any, days_in_month: float = AVERAGE_DAYS_PER_MONTH) -> Any:
    """Estimate ending accounts payable from vendor spend and DPO."""

    result = np.asarray(vendor_expenses_eur, dtype=float) * np.asarray(dpo_days, dtype=float) / days_in_month
    return float(result) if result.ndim == 0 else result


def calculate_collections(
    beginning_ar_eur: Any,
    invoices_eur: Any,
    ending_ar_eur: Any,
    writeoffs_eur: Any = 0.0,
) -> Any:
    """Apply the AR roll-forward: beginning AR + invoices - collections - write-offs."""

    result = (
        np.asarray(beginning_ar_eur, dtype=float)
        + np.asarray(invoices_eur, dtype=float)
        - np.asarray(ending_ar_eur, dtype=float)
        - np.asarray(writeoffs_eur, dtype=float)
    )
    return float(result) if result.ndim == 0 else result


def build_working_capital(
    monthly_data: pd.DataFrame,
    assumptions: Mapping[str, Any] | WorkingCapitalAssumptions | None = None,
) -> pd.DataFrame:
    """Build reconciled AR/AP schedules and their cash consequences.

    Existing AR/AP balances are respected by default. Set
    ``respect_reported_balances=False`` to rebuild balances from DSO/DPO.
    """

    defaults = {
        "dso_days": 55.0,
        "dpo_days": 35.0,
        "writeoff_rate": 0.001,
        "other_current_assets_percent_revenue": 0.02,
        "opening_ar_eur": None,
        "opening_ap_eur": None,
        "respect_reported_balances": True,
    }
    if isinstance(assumptions, WorkingCapitalAssumptions):
        assumptions = {
            "dso_days": assumptions.dso_days,
            "dpo_days": assumptions.dpo_days,
            "writeoff_rate": assumptions.writeoff_rate,
            "other_current_assets_percent_revenue": assumptions.other_current_assets_percent_revenue,
        }
    options = merge_options(defaults, assumptions)
    result = sorted_monthly(monthly_data)
    if "revenue_eur" not in result:
        raise ValueError("monthly_data must include revenue_eur.")

    count = len(result)
    revenue = pd.to_numeric(result["revenue_eur"], errors="coerce").fillna(0.0).to_numpy(float)
    dso_source = first_existing(result, ("dso", "dso_days"))
    dpo_source = first_existing(result, ("dpo", "dpo_days"))
    dso = (
        pd.to_numeric(result[dso_source], errors="coerce").fillna(float(options["dso_days"])).to_numpy(float)
        if dso_source
        else monthly_values(options["dso_days"], count, 55.0)
    )
    dpo = (
        pd.to_numeric(result[dpo_source], errors="coerce").fillna(float(options["dpo_days"])).to_numpy(float)
        if dpo_source
        else monthly_values(options["dpo_days"], count, 35.0)
    )
    dso = np.clip(dso, 0.0, 180.0)
    dpo = np.clip(dpo, 0.0, 180.0)

    ar_column = first_existing(result, ("accounts_receivable_eur", "ending_ar_eur"))
    if ar_column and bool(options["respect_reported_balances"]):
        ending_ar = pd.to_numeric(result[ar_column], errors="coerce").to_numpy(float)
        calculated_ar = calculate_ar(revenue, dso)
        ending_ar = np.where(np.isfinite(ending_ar), ending_ar, calculated_ar)
    else:
        ending_ar = calculate_ar(revenue, dso)

    writeoffs = revenue * float(options["writeoff_rate"])
    beginning_ar = np.r_[
        float(options["opening_ar_eur"]) if options["opening_ar_eur"] is not None else ending_ar[0],
        ending_ar[:-1],
    ]
    collections = np.maximum(calculate_collections(beginning_ar, revenue, ending_ar, writeoffs), 0.0)

    if "vendor_expenses_eur" in result:
        vendor_expenses = pd.to_numeric(result["vendor_expenses_eur"], errors="coerce").fillna(0.0).to_numpy(float)
    else:
        vendor_expenses = np.zeros(count)
        for column in ("contractor_cost_eur", "other_opex_eur", "cloud_cost_eur", "software_cost_eur"):
            if column in result:
                vendor_expenses += pd.to_numeric(result[column], errors="coerce").fillna(0.0).to_numpy(float)

    ap_column = first_existing(result, ("accounts_payable_eur", "ending_ap_eur"))
    if ap_column and bool(options["respect_reported_balances"]):
        ending_ap = pd.to_numeric(result[ap_column], errors="coerce").to_numpy(float)
        calculated_ap = calculate_ap(vendor_expenses, dpo)
        ending_ap = np.where(np.isfinite(ending_ap), ending_ap, calculated_ap)
    else:
        ending_ap = calculate_ap(vendor_expenses, dpo)
    beginning_ap = np.r_[
        float(options["opening_ap_eur"]) if options["opening_ap_eur"] is not None else ending_ap[0],
        ending_ap[:-1],
    ]
    vendor_payments = np.maximum(beginning_ap + vendor_expenses - ending_ap, 0.0)

    other_current_assets = revenue * float(options["other_current_assets_percent_revenue"])
    prior_oca = np.r_[other_current_assets[0], other_current_assets[:-1]]
    change_ar = ending_ar - beginning_ar
    change_ap = ending_ap - beginning_ap

    result["dso"] = dso
    result["dpo"] = dpo
    result["beginning_ar_eur"] = beginning_ar
    result["invoices_eur"] = revenue
    result["writeoffs_eur"] = writeoffs
    result["cash_collections_eur"] = collections
    result["accounts_receivable_eur"] = ending_ar
    result["beginning_ap_eur"] = beginning_ap
    result["vendor_expenses_eur"] = vendor_expenses
    result["vendor_payments_eur"] = vendor_payments
    result["accounts_payable_eur"] = ending_ap
    result["other_current_assets_eur"] = other_current_assets
    result["change_in_ar_eur"] = change_ar
    result["change_in_ap_eur"] = change_ap
    result["change_in_working_capital_eur"] = change_ar - change_ap + (other_current_assets - prior_oca)
    return result


def invoice_aging(invoices: pd.DataFrame, as_of_date: str | pd.Timestamp) -> pd.DataFrame:
    """Return open invoice amounts summarized into standard aging buckets."""

    if invoices.empty:
        return pd.DataFrame(columns=["aging_bucket", "invoice_count", "amount_eur"])
    as_of = pd.Timestamp(as_of_date).normalize()
    date_column = first_existing(invoices, ("expected_payment_date", "due_date", "invoice_date"))
    amount_column = first_existing(invoices, ("amount_eur", "invoice_amount_eur", "amount"))
    if date_column is None or amount_column is None:
        raise ValueError("Invoices need an amount and expected payment/due date.")
    work = invoices.copy()
    due = pd.to_datetime(work[date_column], errors="coerce")
    actual = (
        pd.to_datetime(work["actual_payment_date"], errors="coerce")
        if "actual_payment_date" in work
        else pd.Series(pd.NaT, index=work.index, dtype="datetime64[ns]")
    )
    open_mask = actual.isna() | (actual > as_of)
    work = work.loc[open_mask].copy()
    days_overdue = (as_of - due.loc[open_mask]).dt.days.fillna(0)
    work["aging_bucket"] = pd.cut(
        days_overdue,
        bins=[-np.inf, 0, 30, 60, 90, np.inf],
        labels=["Current", "1-30", "31-60", "61-90", "90+"],
        right=True,
    )
    work["amount_eur"] = pd.to_numeric(work[amount_column], errors="coerce").fillna(0.0)
    return (
        work.groupby("aging_bucket", observed=False)
        .agg(invoice_count=("amount_eur", "size"), amount_eur=("amount_eur", "sum"))
        .reset_index()
    )


def forecast_invoice_collections(
    invoices: pd.DataFrame,
    start_date: str | pd.Timestamp,
    weeks: int = 13,
    collection_delay_days: int = 0,
) -> pd.DataFrame:
    """Place open invoice receipts into weekly collection buckets."""

    start = pd.Timestamp(start_date).normalize()
    start = start - pd.Timedelta(days=start.weekday())
    week_starts = pd.date_range(start, periods=weeks, freq="W-MON")
    result = pd.DataFrame({"week_start": week_starts, "invoice_collections_eur": 0.0})
    if invoices is None or invoices.empty:
        return result
    amount_column = first_existing(invoices, ("amount_eur", "invoice_amount_eur", "amount"))
    expected_column = first_existing(invoices, ("expected_payment_date", "due_date"))
    if amount_column is None or expected_column is None:
        raise ValueError("Invoices need amount_eur and expected_payment_date/due_date.")

    work = invoices.copy()
    expected = pd.to_datetime(work[expected_column], errors="coerce")
    actual = (
        pd.to_datetime(work["actual_payment_date"], errors="coerce")
        if "actual_payment_date" in work
        else pd.Series(pd.NaT, index=work.index, dtype="datetime64[ns]")
    )
    # Known future actual payments supersede the expected date; otherwise forecast open items.
    payment_date = actual.where(actual.notna() & (actual >= start), expected)
    if "status" in work:
        paid_before_start = work["status"].astype(str).str.casefold().eq("paid") & (
            actual.notna() & (actual < start)
        )
    else:
        paid_before_start = actual.notna() & (actual < start)
    original_payment_date = payment_date.copy()
    payment_date = payment_date + pd.to_timedelta(collection_delay_days, unit="D")
    amount = pd.to_numeric(work[amount_column], errors="coerce").fillna(0.0)
    valid = ~paid_before_start & payment_date.notna()
    result.attrs["pre_start_collections_eur"] = float(
        amount.loc[
            valid
            & (original_payment_date >= start)
            & (payment_date < start)
        ].sum()
    )
    collection_week = payment_date.loc[valid] - pd.to_timedelta(payment_date.loc[valid].dt.weekday, unit="D")
    scheduled = amount.loc[valid].groupby(collection_week).sum()
    result["invoice_collections_eur"] = result["week_start"].map(scheduled).fillna(0.0)
    return result


# Short alias used by the liquidity module.
collection_schedule = forecast_invoice_collections
