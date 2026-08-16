"""Simplified, internally reconciled three-statement model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from ._utils import first_existing, merge_options, sorted_monthly
from .working_capital import calculate_ap, calculate_ar


DEFAULT_STATEMENT_ASSUMPTIONS: dict[str, Any] = {
    "tax_rate": 0.16,
    "annual_interest_rate": 0.05,
    "depreciation_useful_life_months": 36,
    "existing_fixed_asset_monthly_depreciation_rate": 1.0 / 60.0,
    "other_current_assets_percent_revenue": 0.02,
    "accrued_expenses_percent_payroll": 0.12,
    "dso_days": 55.0,
    "dpo_days": 35.0,
    "opening_cash_eur": 5_000_000.0,
    "opening_net_fixed_assets_eur": 1_200_000.0,
    "opening_tax_payable_eur": 0.0,
    "opening_debt_eur": 0.0,
}


def _array(frame: pd.DataFrame, names: Sequence[str], default: float = 0.0) -> np.ndarray:
    column = first_existing(frame, names)
    if column is None:
        return np.full(len(frame), float(default))
    return pd.to_numeric(frame[column], errors="coerce").fillna(default).to_numpy(float)


def build_statements(
    monthly_data: pd.DataFrame,
    assumptions: Mapping[str, Any] | None = None,
    opening_balance_sheet: Mapping[str, float] | None = None,
) -> dict[str, pd.DataFrame]:
    """Build reconciled monthly income statement, balance sheet and cash flow.

    Expenses are supplied as positive values. Capex affects investing cash flow
    and fixed assets, but not EBITDA. Opening equity is calculated as the amount
    that balances the explicitly supplied opening assets and liabilities.
    """

    options = merge_options(DEFAULT_STATEMENT_ASSUMPTIONS, assumptions)
    if opening_balance_sheet:
        options.update(dict(opening_balance_sheet))
    data = sorted_monthly(monthly_data)
    if "revenue_eur" not in data:
        raise ValueError("monthly_data must include revenue_eur.")
    count = len(data)
    month = data["month"]

    revenue = _array(data, ("revenue_eur",))
    payroll = _array(data, ("payroll_eur", "employee_cost_eur"))
    contractor = _array(data, ("contractor_cost_eur",))
    other_opex = _array(data, ("other_opex_eur", "operating_expenses_eur"))
    capex = _array(data, ("capex_eur", "capital_expenditure_eur"))
    ebitda = revenue - payroll - contractor - other_opex

    dso = _array(data, ("dso", "dso_days"), float(options["dso_days"]))
    dpo = _array(data, ("dpo", "dpo_days"), float(options["dpo_days"]))
    vendor_expenses = _array(data, ("vendor_expenses_eur",), 0.0)
    if not np.any(vendor_expenses):
        vendor_expenses = contractor + other_opex
    if "accounts_receivable_eur" in data:
        ending_ar = _array(data, ("accounts_receivable_eur",))
    else:
        ending_ar = calculate_ar(revenue, dso)
    if "accounts_payable_eur" in data:
        ending_ap = _array(data, ("accounts_payable_eur",))
    else:
        ending_ap = calculate_ap(vendor_expenses, dpo)
    if "other_current_assets_eur" in data:
        ending_oca = _array(data, ("other_current_assets_eur",))
    else:
        ending_oca = revenue * float(options["other_current_assets_percent_revenue"])
    if "accrued_expenses_eur" in data:
        ending_accrued = _array(data, ("accrued_expenses_eur",))
    else:
        ending_accrued = payroll * float(options["accrued_expenses_percent_payroll"])

    borrowings = _array(data, ("debt_borrowings_eur", "borrowings_eur"))
    repayments = _array(data, ("debt_repayments_eur", "repayments_eur"))
    dividends = _array(data, ("dividends_eur",))
    supplied_depreciation = _array(data, ("depreciation_eur",), np.nan)
    supplied_interest = _array(data, ("interest_eur", "interest_expense_eur"), np.nan)
    supplied_tax = _array(data, ("tax_eur", "tax_expense_eur"), np.nan)
    supplied_tax_paid = _array(data, ("tax_payments_eur", "tax_paid_eur"), np.nan)

    opening_ar = float(options.get("opening_accounts_receivable_eur", ending_ar[0]))
    opening_ap = float(options.get("opening_accounts_payable_eur", ending_ap[0]))
    opening_oca = float(options.get("opening_other_current_assets_eur", ending_oca[0]))
    opening_accrued = float(options.get("opening_accrued_expenses_eur", ending_accrued[0]))
    opening_cash = float(options["opening_cash_eur"])
    opening_nfa = float(options["opening_net_fixed_assets_eur"])
    opening_tax_payable = float(options["opening_tax_payable_eur"])
    opening_debt = float(options["opening_debt_eur"])
    opening_equity = float(
        options.get(
            "opening_equity_eur",
            opening_cash + opening_ar + opening_oca + opening_nfa
            - opening_ap - opening_accrued - opening_tax_payable - opening_debt,
        )
    )

    beginning_cash = np.zeros(count)
    closing_cash = np.zeros(count)
    beginning_ar = np.zeros(count)
    beginning_ap = np.zeros(count)
    beginning_oca = np.zeros(count)
    beginning_accrued = np.zeros(count)
    beginning_tax_payable = np.zeros(count)
    ending_tax_payable = np.zeros(count)
    beginning_nfa = np.zeros(count)
    ending_nfa = np.zeros(count)
    beginning_debt = np.zeros(count)
    ending_debt = np.zeros(count)
    beginning_equity = np.zeros(count)
    ending_equity = np.zeros(count)
    depreciation = np.zeros(count)
    interest = np.zeros(count)
    tax_expense = np.zeros(count)
    tax_paid = np.zeros(count)
    ebit = np.zeros(count)
    pretax_income = np.zeros(count)
    net_income = np.zeros(count)
    operating_cash_flow = np.zeros(count)
    investing_cash_flow = -capex.copy()
    financing_cash_flow = borrowings - repayments - dividends
    net_change_cash = np.zeros(count)

    previous_tax_expense = 0.0
    for index in range(count):
        beginning_cash[index] = opening_cash if index == 0 else closing_cash[index - 1]
        beginning_ar[index] = opening_ar if index == 0 else ending_ar[index - 1]
        beginning_ap[index] = opening_ap if index == 0 else ending_ap[index - 1]
        beginning_oca[index] = opening_oca if index == 0 else ending_oca[index - 1]
        beginning_accrued[index] = opening_accrued if index == 0 else ending_accrued[index - 1]
        beginning_tax_payable[index] = opening_tax_payable if index == 0 else ending_tax_payable[index - 1]
        beginning_nfa[index] = opening_nfa if index == 0 else ending_nfa[index - 1]
        beginning_debt[index] = opening_debt if index == 0 else ending_debt[index - 1]
        beginning_equity[index] = opening_equity if index == 0 else ending_equity[index - 1]

        if np.isfinite(supplied_depreciation[index]):
            depreciation[index] = max(supplied_depreciation[index], 0.0)
        else:
            existing_asset_depreciation = (
                beginning_nfa[index] * float(options["existing_fixed_asset_monthly_depreciation_rate"])
            )
            new_asset_depreciation = capex[index] / float(options["depreciation_useful_life_months"])
            depreciation[index] = min(existing_asset_depreciation + new_asset_depreciation, beginning_nfa[index] + capex[index])
        ebit[index] = ebitda[index] - depreciation[index]
        interest[index] = (
            supplied_interest[index]
            if np.isfinite(supplied_interest[index])
            else beginning_debt[index] * float(options["annual_interest_rate"]) / 12.0
        )
        pretax_income[index] = ebit[index] - interest[index]
        tax_expense[index] = (
            supplied_tax[index]
            if np.isfinite(supplied_tax[index])
            else max(pretax_income[index], 0.0) * float(options["tax_rate"])
        )
        net_income[index] = pretax_income[index] - tax_expense[index]
        scheduled_tax_paid = (
            supplied_tax_paid[index]
            if np.isfinite(supplied_tax_paid[index])
            else previous_tax_expense
        )
        tax_paid[index] = min(max(scheduled_tax_paid, 0.0), beginning_tax_payable[index] + tax_expense[index])
        ending_tax_payable[index] = beginning_tax_payable[index] + tax_expense[index] - tax_paid[index]
        previous_tax_expense = tax_expense[index]

        ending_nfa[index] = beginning_nfa[index] + capex[index] - depreciation[index]
        ending_debt[index] = beginning_debt[index] + borrowings[index] - repayments[index]

        delta_ar = ending_ar[index] - beginning_ar[index]
        delta_ap = ending_ap[index] - beginning_ap[index]
        delta_oca = ending_oca[index] - beginning_oca[index]
        delta_accrued = ending_accrued[index] - beginning_accrued[index]
        delta_tax_payable = ending_tax_payable[index] - beginning_tax_payable[index]
        operating_cash_flow[index] = (
            net_income[index]
            + depreciation[index]
            - delta_ar
            - delta_oca
            + delta_ap
            + delta_accrued
            + delta_tax_payable
        )
        net_change_cash[index] = (
            operating_cash_flow[index] + investing_cash_flow[index] + financing_cash_flow[index]
        )
        closing_cash[index] = beginning_cash[index] + net_change_cash[index]
        ending_equity[index] = beginning_equity[index] + net_income[index] - dividends[index]

    income_statement = pd.DataFrame(
        {
            "month": month,
            "revenue_eur": revenue,
            "payroll_eur": payroll,
            "contractor_cost_eur": contractor,
            "other_opex_eur": other_opex,
            "ebitda_eur": ebitda,
            "ebitda_margin": np.divide(ebitda, revenue, out=np.zeros(count), where=revenue != 0),
            "depreciation_eur": depreciation,
            "ebit_eur": ebit,
            "interest_eur": interest,
            "profit_before_tax_eur": pretax_income,
            "tax_expense_eur": tax_expense,
            "net_income_eur": net_income,
        }
    )

    total_assets = closing_cash + ending_ar + ending_oca + ending_nfa
    total_liabilities = ending_ap + ending_accrued + ending_tax_payable + ending_debt
    total_liabilities_equity = total_liabilities + ending_equity
    balance_sheet = pd.DataFrame(
        {
            "month": month,
            "cash_eur": closing_cash,
            "accounts_receivable_eur": ending_ar,
            "other_current_assets_eur": ending_oca,
            "net_fixed_assets_eur": ending_nfa,
            "total_assets_eur": total_assets,
            "accounts_payable_eur": ending_ap,
            "accrued_expenses_eur": ending_accrued,
            "tax_payable_eur": ending_tax_payable,
            "debt_eur": ending_debt,
            "total_liabilities_eur": total_liabilities,
            "equity_eur": ending_equity,
            "total_liabilities_and_equity_eur": total_liabilities_equity,
        }
    )

    cash_flow = pd.DataFrame(
        {
            "month": month,
            "opening_cash_eur": beginning_cash,
            "operating_cash_flow_eur": operating_cash_flow,
            "investing_cash_flow_eur": investing_cash_flow,
            "financing_cash_flow_eur": financing_cash_flow,
            "net_change_in_cash_eur": net_change_cash,
            "closing_cash_eur": closing_cash,
            "tax_payments_eur": tax_paid,
            "capex_eur": capex,
        }
    )

    balance_difference = total_assets - total_liabilities_equity
    cash_difference = closing_cash - (beginning_cash + net_change_cash)
    checks = pd.DataFrame(
        {
            "month": month,
            "balance_difference_eur": balance_difference,
            "cash_reconciliation_difference_eur": cash_difference,
            "balance_sheet_reconciles": np.abs(balance_difference) <= 1.0,
            "cash_reconciles": np.abs(cash_difference) <= 1.0,
        }
    )
    checks["is_reconciled"] = checks["balance_sheet_reconciles"] & checks["cash_reconciles"]

    combined = (
        income_statement
        .merge(balance_sheet, on="month", how="left")
        .merge(cash_flow, on="month", how="left")
        .merge(checks, on="month", how="left")
    )
    return {
        "income_statement": income_statement,
        "balance_sheet": balance_sheet,
        "cash_flow": cash_flow,
        "checks": checks,
        "combined": combined,
    }


def check_reconciliation(
    statements: Mapping[str, pd.DataFrame] | pd.DataFrame,
    tolerance_eur: float = 1.0,
) -> dict[str, Any]:
    """Summarize the accounting and cash reconciliation checks."""

    checks = statements.get("checks") if isinstance(statements, Mapping) else statements
    if checks is None or checks.empty:
        raise ValueError("No reconciliation checks were supplied.")
    balance = pd.to_numeric(checks["balance_difference_eur"], errors="coerce").abs()
    cash = pd.to_numeric(checks["cash_reconciliation_difference_eur"], errors="coerce").abs()
    failed = (balance > tolerance_eur) | (cash > tolerance_eur)
    return {
        "is_reconciled": bool(not failed.any()),
        "max_balance_difference_eur": float(balance.max()),
        "max_cash_difference_eur": float(cash.max()),
        "failed_periods": int(failed.sum()),
        "tolerance_eur": float(tolerance_eur),
    }


def assert_reconciled(
    statements: Mapping[str, pd.DataFrame] | pd.DataFrame,
    tolerance_eur: float = 1.0,
) -> None:
    """Raise ``AssertionError`` when either accounting identity fails."""

    result = check_reconciliation(statements, tolerance_eur)
    if not result["is_reconciled"]:
        raise AssertionError(
            "Statements do not reconcile: "
            f"balance difference={result['max_balance_difference_eur']:.2f}, "
            f"cash difference={result['max_cash_difference_eur']:.2f}."
        )


# Readable alias for notebook and UI callers.
reconciliation_checks = check_reconciliation
