"""Generate deterministic, causally linked demonstration data for NovaPlan.

The generator deliberately starts with operating drivers.  Workforce, backlog and
utilization produce revenue; revenue produces invoices; invoice and vendor timing
then produce working-capital balances and cash.  Nothing in this module represents
a real company or authoritative tax/accounting guidance.
"""

from __future__ import annotations

import argparse
import calendar
import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


SEED = 42
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data"
ASSUMPTIONS_PATH = PROJECT_ROOT / "config" / "assumptions.yaml"

LEVEL_ORDER = [
    "Junior",
    "Mid",
    "Senior",
    "Manager / Leadership",
    "Non-billable support",
]


def _load_assumptions() -> dict[str, Any]:
    """Load the human-readable illustrative assumptions used by the generator."""

    with ASSUMPTIONS_PATH.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _working_days(month: pd.Timestamp) -> int:
    """Return a stable approximation of Romanian business days in a month."""

    next_month = month + pd.offsets.MonthBegin(1)
    weekdays = int(np.busday_count(month.date(), next_month.date()))
    # Illustrative weekday public-holiday allowance, intentionally not a tax/legal calendar.
    holiday_allowance = {1: 2, 4: 2, 5: 1, 6: 1, 8: 1, 11: 1, 12: 3}
    return max(17, weekdays - holiday_allowance.get(month.month, 0))


def _phase_demand(month: pd.Timestamp) -> float:
    """Demand cycle used to create recovery, expansion, pressure and response phases."""

    year, number = month.year, month.month
    if year == 2020:
        if number <= 2:
            return 0.01
        if number <= 6:
            return -0.11
        if number <= 10:
            return -0.055
        return -0.015
    if year == 2021:
        return 0.005 + 0.0045 * number
    if year == 2022:
        return 0.06 + 0.002 * min(number, 8)
    if year == 2023:
        if number <= 6:
            return 0.075
        if number <= 10:
            return -0.025
        return 0.005
    if year == 2024:
        if number <= 3:
            return -0.005
        if number <= 8:
            return 0.018
        return 0.038
    return 0.045 + 0.0025 * number


def _collection_stress(invoice_date: pd.Timestamp, is_key_account: bool) -> float:
    """Extra collection delay during the two realistic stress periods."""

    if pd.Timestamp("2020-03-01") <= invoice_date <= pd.Timestamp("2020-09-30"):
        return 7.0
    if pd.Timestamp("2023-07-01") <= invoice_date <= pd.Timestamp("2024-02-29"):
        return 14.0 if is_key_account else 9.0
    return 0.0


def _allocate_counts(total: int, probabilities: np.ndarray) -> np.ndarray:
    """Allocate an integer total while preserving the requested mix."""

    raw = total * probabilities
    counts = np.floor(raw).astype(int)
    for index in np.argsort(raw - counts)[::-1][: total - counts.sum()]:
        counts[index] += 1
    return counts


def _make_customers(rng: np.random.Generator) -> pd.DataFrame:
    """Create fictional customers with concentration and distinct payment behavior."""

    names = [
        "Rheinwerk Industries GmbH",
        "Nordbyte Technology AB",
        "Alpine Consumer Group AG",
        "Westhaven Financial NV",
        "Meridian Mobility SAS",
        "Baltic Grid Solutions OY",
        "Orion Health Systems BV",
        "Fjord Commerce AS",
        "Lumen Manufacturing GmbH",
        "Crownfield Retail Ltd",
        "Danube Energy Services GmbH",
        "Helix Media Group SAS",
        "Northstar Logistics BV",
        "Evergreen Telecom AB",
        "Aster Insurance SA",
        "Bluegate Foods GmbH",
        "Keystone Travel Ltd",
        "Solstice Devices OY",
        "Oakline Property NV",
        "Vector Automotive GmbH",
        "Clarion Learning AB",
        "Ember Utilities SAS",
        "Silverpeak Analytics BV",
        "Willow Pharma AG",
    ]
    countries = [
        "Germany", "Sweden", "Switzerland", "Netherlands", "France", "Finland",
        "Netherlands", "Norway", "Germany", "United Kingdom", "Germany", "France",
        "Netherlands", "Sweden", "Belgium", "Germany", "United Kingdom", "Finland",
        "Belgium", "Germany", "Sweden", "France", "Netherlands", "Switzerland",
    ]
    industries = [
        "Industrial", "Technology", "Consumer", "Financial Services", "Automotive",
        "Energy", "Healthcare", "Retail", "Manufacturing", "Retail", "Energy", "Media",
        "Logistics", "Telecom", "Insurance", "Food", "Travel", "Technology",
        "Real Estate", "Automotive", "Education", "Utilities", "Technology", "Healthcare",
    ]
    terms = [45, 30, 60, 60, 45, 45, 30, 30, 45, 60, 45, 45, 45, 30, 60, 45, 30, 45, 60, 60, 30, 45, 30, 60]
    typical_delays = [7, -1, 11, 12, 5, 3, 0, 2, 6, 9, 4, 5, 2, 0, 10, 4, 1, 3, 8, 12, 0, 4, -1, 9]
    weights = np.array([0.16, 0.13, 0.11, 0.085, 0.065] + [0.45 / 19] * 19)
    service_lines = [
        "Digital Transformation", "Software Engineering", "Data & AI", "Cloud Engineering"
    ]
    rows: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        rows.append(
            {
                "customer_id": f"CUS-{index + 1:03d}",
                "customer_name": name,
                "country": countries[index],
                "industry": industries[index],
                "segment": "Strategic" if index < 5 else ("Enterprise" if index < 14 else "Growth"),
                "primary_service_line": service_lines[index % len(service_lines)],
                "contract_start_date": pd.Timestamp("2017-01-01")
                + pd.to_timedelta(int(rng.integers(0, 1_000)), unit="D"),
                "payment_terms_days": terms[index],
                "typical_delay_days": typical_delays[index],
                "delay_volatility_days": 3 if index in {1, 6, 13, 20, 22} else 6,
                "annual_contract_value_eur": round(22_000_000 * weights[index], 2),
                "credit_risk": "Low" if typical_delays[index] <= 3 else ("Moderate" if typical_delays[index] <= 8 else "Watch"),
                "revenue_weight": weights[index],
                "is_key_account": index < 5,
            }
        )
    return pd.DataFrame(rows)


def _new_employee(
    employee_number: int,
    level: str,
    hire_date: pd.Timestamp,
    salary_index: float,
    assumptions: dict[str, Any],
    rng: np.random.Generator,
) -> dict[str, Any]:
    level_config = assumptions["workforce"]["levels"][level]
    roles = {
        "Junior": ["Junior Consultant", "Software Engineer"],
        "Mid": ["Consultant", "Data Engineer", "Software Engineer"],
        "Senior": ["Senior Consultant", "Solution Architect", "Senior Engineer"],
        "Manager / Leadership": ["Engagement Manager", "Delivery Lead", "Director"],
        "Non-billable support": ["Finance", "People Operations", "Sales Operations", "IT Support"],
    }
    salary = level_config["annual_salary_2020_eur"] * salary_index * rng.lognormal(0, 0.07)
    return {
        "employee_id": f"EMP-{employee_number:04d}",
        "location": "Bucharest" if rng.random() < 0.67 else "Cluj-Napoca",
        "seniority": level,
        "role": str(rng.choice(roles[level])),
        "billable": bool(level_config["billable"]),
        "hire_date": pd.Timestamp(hire_date),
        "annual_base_salary_eur": float(salary),
        "bonus_percent": float(level_config["bonus_percent"]),
        "employer_oncost_rate": float(assumptions["workforce"]["employer_oncost_rate"]),
        "benefits_monthly_eur": float(assumptions["workforce"]["benefits_per_employee_month_eur"]),
        "expected_utilization": float(level_config["expected_utilization"]),
    }


def _generate_operations(
    assumptions: dict[str, Any], rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate workforce, capacity, demand, backlog and revenue month by month."""

    months = pd.date_range(
        assumptions["simulation"]["history_start"],
        assumptions["simulation"]["history_end"],
        freq="MS",
    )
    workforce = assumptions["workforce"]
    level_config = workforce["levels"]
    opening_mix = np.array([level_config[level]["opening_mix"] for level in LEVEL_ORDER])
    opening_counts = _allocate_counts(int(workforce["opening_headcount"]), opening_mix)

    active: list[dict[str, Any]] = []
    next_employee = 1
    for level, count in zip(LEVEL_ORDER, opening_counts, strict=True):
        for _ in range(int(count)):
            hire_date = pd.Timestamp("2014-01-01") + pd.to_timedelta(int(rng.integers(0, 2_180)), unit="D")
            active.append(_new_employee(next_employee, level, hire_date, 1.0, assumptions, rng))
            next_employee += 1

    salary_reviews = {2020: 0.045, 2021: 0.052, 2022: 0.078, 2023: 0.092, 2024: 0.068, 2025: 0.058}
    rate_reviews = {2020: 0.0, 2021: 0.025, 2022: 0.034, 2023: 0.046, 2024: 0.048, 2025: 0.041}
    salary_index = 1.0
    rate_index = 1.0
    previous_backlog = float(assumptions["revenue"]["opening_backlog_eur"])
    previous_utilization = 0.735
    previous_revenue = 1_650_000.0
    previous_backlog_cover = previous_backlog / previous_revenue
    rows: list[dict[str, Any]] = []

    for month in months:
        if month.month == int(workforce["annual_salary_review_month"]):
            raise_rate = salary_reviews[month.year]
            salary_index *= 1 + raise_rate
            for employee in active:
                employee["annual_base_salary_eur"] *= 1 + raise_rate
                employee["benefits_monthly_eur"] *= 1 + min(raise_rate, 0.05)
        if month.month == int(assumptions["revenue"]["annual_rate_review_month"]):
            rate_index *= 1 + rate_reviews[month.year]

        beginning_headcount = len(active)
        monthly_attrition_rate = 0.0095
        if pd.Timestamp("2022-07-01") <= month <= pd.Timestamp("2023-06-01"):
            monthly_attrition_rate += 0.002
        if pd.Timestamp("2023-07-01") <= month <= pd.Timestamp("2024-02-01"):
            monthly_attrition_rate += 0.0015
        attrition = int(np.clip(rng.poisson(beginning_headcount * monthly_attrition_rate), 1, 8))
        departing_indices = sorted(
            rng.choice(len(active), size=min(attrition, len(active)), replace=False).tolist(), reverse=True
        )
        for departing_index in departing_indices:
            active.pop(departing_index)
        attrition = len(departing_indices)

        hiring_signal = max(0.0, (previous_utilization - 0.71) * 45 + (previous_backlog_cover - 2.5) * 1.2)
        base_hires = 3.0 + hiring_signal
        if pd.Timestamp("2020-03-01") <= month <= pd.Timestamp("2020-10-01"):
            base_hires *= 0.20
        elif month.year == 2021:
            base_hires += 1.5
        elif month.year == 2022:
            base_hires += 4.5
        elif month.year == 2023 and month.month <= 6:
            base_hires += 3.0
        elif pd.Timestamp("2023-07-01") <= month <= pd.Timestamp("2024-03-01"):
            base_hires *= 0.42
        elif month.year == 2025:
            base_hires += 0.8
        new_hires = int(np.clip(round(base_hires + rng.normal(0, 1.0)), 0, 13))

        hire_mix = np.array([0.28, 0.39, 0.20, 0.04, 0.09])
        hire_levels = rng.choice(LEVEL_ORDER, size=new_hires, p=hire_mix)
        for level in hire_levels:
            join_day = int(rng.integers(1, 15))
            hire_date = month + pd.to_timedelta(join_day - 1, unit="D")
            active.append(_new_employee(next_employee, str(level), hire_date, salary_index, assumptions, rng))
            next_employee += 1

        headcount = len(active)
        billable_count = sum(employee["billable"] for employee in active)
        billable_share = billable_count / headcount
        working_days = _working_days(month)
        demand_index = _phase_demand(month)
        backlog_effect = float(np.clip((previous_backlog_cover - 2.8) * 0.009, -0.018, 0.022))
        seasonal_effect = {7: -0.035, 8: -0.072, 12: -0.045}.get(month.month, 0.0)
        utilization = float(
            np.clip(0.728 + 0.62 * demand_index + backlog_effect + seasonal_effect + rng.normal(0, 0.007), 0.59, 0.84)
        )
        realization_rate = float(
            np.clip(assumptions["revenue"]["base_realization_rate"] + rng.normal(0, 0.004) - max(0, -demand_index) * 0.035, 0.935, 0.982)
        )
        unramped_capacity_hours = billable_count * working_days * float(assumptions["simulation"]["hours_per_day"])
        ramp_values = workforce["new_hire_productivity_ramp"]
        productivity_weights = []
        for employee in active:
            if not employee["billable"]:
                continue
            tenure_months = (month.year - employee["hire_date"].year) * 12 + month.month - employee["hire_date"].month
            if tenure_months <= 0:
                productivity_weights.append(float(ramp_values["month_1"]))
            elif tenure_months == 1:
                productivity_weights.append(float(ramp_values["month_2"]))
            elif tenure_months == 2:
                productivity_weights.append(float(ramp_values["month_3"]))
            else:
                productivity_weights.append(float(ramp_values["steady_state"]))
        workforce_ramp_factor = sum(productivity_weights) / max(billable_count, 1)
        billable_capacity_hours = unramped_capacity_hours * workforce_ramp_factor
        billable_hours = billable_capacity_hours * utilization

        weighted_rate = sum(
            level_config[employee["seniority"]]["billing_rate_2020_eur"] * rate_index
            for employee in active
            if employee["billable"]
        ) / max(billable_count, 1)
        contractor_fte = int(
            np.clip(9 + max(0, demand_index) * 65 + max(0, previous_utilization - 0.75) * 90 + rng.normal(0, 1.2), 5, 22)
        )
        contractor_hours = contractor_fte * working_days * 8 * min(utilization + 0.025, 0.86)
        contractor_revenue = contractor_hours * weighted_rate * 1.08 * realization_rate
        employee_revenue = billable_hours * weighted_rate * realization_rate
        revenue = employee_revenue + contractor_revenue
        contractor_cost = contractor_revenue / float(assumptions["revenue"]["contractor_markup"])

        bookings = revenue * (1 + 0.70 * demand_index + rng.normal(0, 0.035))
        ending_backlog = float(np.clip(previous_backlog + bookings - revenue, 2_600_000, 9_500_000))

        monthly_base_pay = sum(employee["annual_base_salary_eur"] / 12 for employee in active)
        bonus_accrual = sum(
            employee["annual_base_salary_eur"] * employee["bonus_percent"] / 12 for employee in active
        )
        oncost = monthly_base_pay * float(workforce["employer_oncost_rate"])
        benefits = sum(employee["benefits_monthly_eur"] for employee in active)
        payroll = monthly_base_pay + bonus_accrual + oncost + benefits

        rows.append(
            {
                "month": month,
                "beginning_headcount": beginning_headcount,
                "headcount": headcount,
                "new_hires": new_hires,
                "attrition": attrition,
                "billable_headcount": billable_count,
                "billable_share": billable_share,
                "utilization": utilization,
                "working_days": working_days,
                "hours_per_day": float(assumptions["simulation"]["hours_per_day"]),
                "workforce_ramp_factor": workforce_ramp_factor,
                "billable_capacity_hours": billable_capacity_hours,
                "billable_hours": billable_hours,
                "billing_rate_eur": weighted_rate,
                "realization_rate": realization_rate,
                "demand_index": demand_index,
                "bookings_eur": bookings,
                "backlog_eur": ending_backlog,
                "contractor_fte": contractor_fte,
                "contractor_revenue_eur": contractor_revenue,
                "revenue_eur": revenue,
                "payroll_eur": payroll,
                "contractor_cost_eur": contractor_cost,
                "salary_inflation": salary_reviews[month.year],
            }
        )
        previous_backlog = ending_backlog
        previous_utilization = utilization
        previous_revenue = revenue
        previous_backlog_cover = ending_backlog / max(revenue, 1)

    current_rate_index = rate_index
    employees = pd.DataFrame(active).copy()
    employees["monthly_base_salary_eur"] = employees["annual_base_salary_eur"] / 12
    employees["expected_billing_rate_eur"] = employees["seniority"].map(
        {level: level_config[level]["billing_rate_2020_eur"] * current_rate_index for level in LEVEL_ORDER}
    )
    employees["status"] = "Active"
    employees["as_of_date"] = pd.Timestamp(assumptions["simulation"]["as_of_date"])
    employees = employees[
        [
            "employee_id", "location", "role", "seniority", "billable", "hire_date",
            "annual_base_salary_eur", "monthly_base_salary_eur", "employer_oncost_rate",
            "bonus_percent", "benefits_monthly_eur", "expected_billing_rate_eur",
            "expected_utilization", "status", "as_of_date",
        ]
    ]
    return pd.DataFrame(rows), employees


def _generate_invoices(
    monthly: pd.DataFrame,
    customers: pd.DataFrame,
    assumptions: dict[str, Any],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Turn recognized monthly revenue into invoices and customer payment events."""

    customer_probabilities = customers["revenue_weight"].to_numpy(dtype=float, copy=True)
    customer_probabilities /= customer_probabilities.sum()
    as_of = pd.Timestamp(assumptions["simulation"]["as_of_date"])
    service_lines = np.array(["Software Engineering", "Data & AI", "Digital Transformation", "Cloud Engineering"])
    service_probabilities = np.array([0.38, 0.24, 0.23, 0.15])
    rows: list[dict[str, Any]] = []
    invoice_number = 1

    for record in monthly.itertuples(index=False):
        month = pd.Timestamp(record.month)
        invoice_count = int(np.clip(round(31 + record.headcount / 30 + rng.normal(0, 2)), 32, 48))
        chosen_customer_indices = rng.choice(
            len(customers), size=invoice_count, p=customer_probabilities
        )
        raw_amounts = rng.gamma(shape=2.7, scale=1.0, size=invoice_count)
        amounts = np.round(float(record.revenue_eur) * raw_amounts / raw_amounts.sum(), 2)
        amounts[-1] += round(float(record.revenue_eur) - float(amounts.sum()), 2)

        for customer_index, amount in zip(chosen_customer_indices, amounts, strict=True):
            customer = customers.iloc[int(customer_index)]
            last_day = calendar.monthrange(month.year, month.month)[1]
            invoice_date = month + pd.to_timedelta(int(rng.integers(1, min(last_day, 27))), unit="D")
            expected_date = invoice_date + pd.to_timedelta(int(customer["payment_terms_days"]), unit="D")
            exceptional_delay = rng.uniform(14, 34) if rng.random() < 0.055 else 0.0
            delay = int(
                round(
                    rng.normal(float(customer["typical_delay_days"]), float(customer["delay_volatility_days"]))
                    + _collection_stress(invoice_date, bool(customer["is_key_account"]))
                    + exceptional_delay
                )
            )
            delay = int(np.clip(delay, -7, 55))
            forecast_payment_date = expected_date + pd.to_timedelta(delay, unit="D")
            is_writeoff = bool(rng.random() < float(assumptions["working_capital"]["writeoff_rate"]))
            writeoff_date = expected_date + pd.to_timedelta(150, unit="D") if is_writeoff else pd.NaT
            if is_writeoff and writeoff_date <= as_of:
                actual_payment_date = pd.NaT
                status = "Written off"
                days_late = int((writeoff_date - expected_date).days)
            elif forecast_payment_date <= as_of:
                actual_payment_date = forecast_payment_date
                status = "Paid"
                days_late = max(0, delay)
                writeoff_date = pd.NaT
            else:
                actual_payment_date = pd.NaT
                status = "Overdue" if expected_date < as_of else "Open"
                days_late = max(0, int((as_of - expected_date).days)) if status == "Overdue" else 0
                writeoff_date = pd.NaT
            rows.append(
                {
                    "invoice_id": f"INV-{invoice_number:06d}",
                    "customer_id": customer["customer_id"],
                    "invoice_date": invoice_date,
                    "amount_eur": float(amount),
                    "payment_terms_days": int(customer["payment_terms_days"]),
                    "expected_payment_date": expected_date,
                    "forecast_payment_date": forecast_payment_date,
                    "actual_payment_date": actual_payment_date,
                    "writeoff_date": writeoff_date,
                    "days_late": days_late,
                    "status": status,
                    "service_line": str(rng.choice(service_lines, p=service_probabilities)),
                }
            )
            invoice_number += 1
    return pd.DataFrame(rows)


def _generate_opex(monthly: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Generate a transparent long-form non-payroll operating-cost schedule."""

    rows: list[dict[str, Any]] = []
    for record in monthly.itertuples(index=False):
        month = pd.Timestamp(record.month)
        years_from_start = (month.year - 2020) + (month.month - 1) / 12
        inflation_index = 1.045**years_from_start
        covid_travel_factor = 0.18 if month.year == 2020 and month.month >= 3 else (0.55 if month.year == 2021 else 1.0)
        summer_travel = 1.25 if month.month in {5, 6, 9, 10} else (0.65 if month.month in {7, 8, 12} else 0.9)
        values = {
            "Contractors": float(record.contractor_cost_eur),
            "Cloud usage": float(record.revenue_eur) * (0.019 + rng.normal(0, 0.0012)),
            "Software licenses": float(record.headcount) * 102 * inflation_index,
            "Travel": float(record.revenue_eur) * 0.018 * covid_travel_factor * summer_travel,
            "Recruitment": float(record.new_hires) * 2_250,
            "Sales commissions": float(record.revenue_eur) * 0.012,
            "Training and delivery support": float(record.revenue_eur) * 0.045,
            "Office rent": 102_000 * inflation_index,
            "Professional services": 72_000 * inflation_index * (1 + rng.normal(0, 0.035)),
            "Insurance and administration": 104_000 * inflation_index * (1 + rng.normal(0, 0.025)),
            "Corporate overhead": 82_000 * inflation_index * (1 + rng.normal(0, 0.025)),
        }
        metadata = {
            "Contractors": ("Variable", "Contractor capacity and delivery demand", 30),
            "Cloud usage": ("Variable", "Revenue and project workload", 30),
            "Software licenses": ("Semi-variable", "Headcount", 30),
            "Travel": ("Variable", "Revenue and delivery seasonality", 20),
            "Recruitment": ("Variable", "New hires", 20),
            "Sales commissions": ("Variable", "Recognized revenue", 30),
            "Training and delivery support": ("Semi-variable", "Revenue and active headcount", 25),
            "Office rent": ("Fixed", "Lease plan", 30),
            "Professional services": ("Fixed", "Annual operating plan", 35),
            "Insurance and administration": ("Fixed", "Annual operating plan", 30),
            "Corporate overhead": ("Fixed", "Annual operating plan", 30),
        }
        for category, amount in values.items():
            cost_type, driver, payment_delay = metadata[category]
            rows.append(
                {
                    "month": month,
                    "category": category,
                    "cost_type": cost_type,
                    "driver": driver,
                    "payment_delay_days": payment_delay,
                    "amount_eur": max(0.0, amount),
                }
            )
    return pd.DataFrame(rows)


def _generate_capex(
    monthly: pd.DataFrame, assumptions: dict[str, Any], rng: np.random.Generator
) -> pd.DataFrame:
    """Create hiring-linked equipment, replacement and occasional strategic capex."""

    capex_config = assumptions["capex"]
    rows: list[dict[str, Any]] = []
    asset_number = 1
    strategic_months = {
        pd.Timestamp("2021-10-01"): ("Office improvements", 165_000, 60),
        pd.Timestamp("2022-11-01"): ("Strategic technology", 245_000, 48),
        pd.Timestamp("2024-06-01"): ("Office improvements", 185_000, 60),
        pd.Timestamp("2025-09-01"): ("Strategic technology", 210_000, 48),
    }
    for record in monthly.itertuples(index=False):
        month = pd.Timestamp(record.month)
        items = [
            (
                "New-hire equipment",
                "New hires",
                float(record.new_hires) * float(capex_config["equipment_per_new_hire_eur"]),
                int(capex_config["laptop_useful_life_months"]),
            ),
            (
                "Laptop replacement",
                "Active headcount / replacement cycle",
                float(record.headcount) / 36 * float(capex_config["replacement_laptop_eur"]) * rng.uniform(0.85, 1.15),
                int(capex_config["laptop_useful_life_months"]),
            ),
        ]
        if month in strategic_months:
            category, amount, life = strategic_months[month]
            items.append((category, "Management investment plan", float(amount), int(life)))
        for category, driver, amount, useful_life in items:
            if amount <= 0:
                continue
            rows.append(
                {
                    "capex_id": f"CAP-{asset_number:04d}",
                    "month": month,
                    "category": category,
                    "description": f"{category} - {month:%b %Y}",
                    "driver": driver,
                    "amount_eur": amount,
                    "useful_life_months": useful_life,
                }
            )
            asset_number += 1
    return pd.DataFrame(rows)


def _depreciation_schedule(months: pd.Series, capex: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Return straight-line depreciation and net fixed assets for each history month."""

    opening_net_fixed_assets = 1_350_000.0
    opening_monthly_depreciation = 32_000.0
    depreciation: list[float] = []
    net_fixed_assets: list[float] = []
    current_nfa = opening_net_fixed_assets
    for month in pd.to_datetime(months):
        current_capex = float(capex.loc[capex["month"] == month, "amount_eur"].sum())
        asset_depreciation = 0.0
        for asset in capex.itertuples(index=False):
            age = (month.year - asset.month.year) * 12 + month.month - asset.month.month
            if 0 <= age < asset.useful_life_months:
                asset_depreciation += asset.amount_eur / asset.useful_life_months
        legacy_depreciation = max(0.0, opening_monthly_depreciation * (1 - len(depreciation) / 60))
        month_depreciation = legacy_depreciation + asset_depreciation
        current_nfa = max(0.0, current_nfa + current_capex - month_depreciation)
        depreciation.append(month_depreciation)
        net_fixed_assets.append(current_nfa)
    return np.array(depreciation), np.array(net_fixed_assets)


def _complete_financials(
    monthly: pd.DataFrame,
    invoices: pd.DataFrame,
    opex: pd.DataFrame,
    capex: pd.DataFrame,
    assumptions: dict[str, Any],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Add working capital, profit, tax and a fully bridged cash balance."""

    monthly = monthly.copy()
    month_index = pd.DatetimeIndex(monthly["month"])
    other_opex = (
        opex.loc[opex["category"] != "Contractors"].groupby("month")["amount_eur"].sum().reindex(month_index).to_numpy()
    )
    vendor_expenses = opex.groupby("month")["amount_eur"].sum().reindex(month_index).to_numpy()
    capex_monthly = capex.groupby("month")["amount_eur"].sum().reindex(month_index).to_numpy()
    monthly["other_opex_eur"] = other_opex
    monthly["vendor_expenses_eur"] = vendor_expenses
    monthly["ebitda_eur"] = (
        monthly["revenue_eur"] - monthly["payroll_eur"] - monthly["contractor_cost_eur"] - monthly["other_opex_eur"]
    )
    monthly["ebitda_margin"] = monthly["ebitda_eur"] / monthly["revenue_eur"]
    monthly["capex_eur"] = capex_monthly
    depreciation, net_fixed_assets = _depreciation_schedule(monthly["month"], capex)
    monthly["depreciation_eur"] = depreciation
    monthly["net_fixed_assets_eur"] = net_fixed_assets
    monthly["ebit_eur"] = monthly["ebitda_eur"] - monthly["depreciation_eur"]
    monthly["interest_eur"] = np.maximum(1_800.0, 6_000.0 - np.arange(len(monthly)) * 55)
    tax_rate = float(assumptions["tax"]["illustrative_corporate_tax_rate"])
    monthly["tax_expense_eur"] = np.maximum(0.0, monthly["ebit_eur"] - monthly["interest_eur"]) * tax_rate
    monthly["net_income_eur"] = monthly["ebit_eur"] - monthly["interest_eur"] - monthly["tax_expense_eur"]

    paid = invoices.loc[invoices["actual_payment_date"].notna()].copy()
    paid["collection_month"] = pd.to_datetime(paid["actual_payment_date"]).dt.to_period("M").dt.to_timestamp()
    invoice_collections = paid.groupby("collection_month")["amount_eur"].sum()
    written_off = invoices.loc[invoices["status"] == "Written off"].copy()
    if not written_off.empty:
        written_off["writeoff_month"] = pd.to_datetime(written_off["writeoff_date"]).dt.to_period("M").dt.to_timestamp()
        writeoffs = written_off.groupby("writeoff_month")["amount_eur"].sum()
    else:
        writeoffs = pd.Series(dtype=float)
    opening_ar = float(assumptions["working_capital"]["opening_accounts_receivable_eur"])
    opening_ar_collections = {0: opening_ar * 0.43, 1: opening_ar * 0.39, 2: opening_ar * 0.18}
    ar_balances: list[float] = []
    beginning_ar_values: list[float] = []
    collection_values: list[float] = []
    writeoff_values: list[float] = []
    current_ar = opening_ar
    for index, record in monthly.iterrows():
        month = pd.Timestamp(record["month"])
        collections = float(invoice_collections.get(month, 0.0)) + opening_ar_collections.get(index, 0.0)
        month_writeoffs = float(writeoffs.get(month, 0.0))
        beginning_ar_values.append(current_ar)
        current_ar = max(0.0, current_ar + float(record["revenue_eur"]) - collections - month_writeoffs)
        collection_values.append(collections)
        writeoff_values.append(month_writeoffs)
        ar_balances.append(current_ar)
    monthly["beginning_ar_eur"] = beginning_ar_values
    monthly["cash_collections_eur"] = collection_values
    monthly["writeoffs_eur"] = writeoff_values
    monthly["accounts_receivable_eur"] = ar_balances
    trailing_revenue = monthly["revenue_eur"].rolling(3, min_periods=1).mean()
    monthly["dso"] = monthly["accounts_receivable_eur"] / trailing_revenue * 30.4375

    beginning_ap = float(assumptions["working_capital"]["opening_accounts_payable_eur"])
    ap_balances: list[float] = []
    beginning_ap_values: list[float] = []
    vendor_payments: list[float] = []
    dpo_values: list[float] = []
    current_ap = beginning_ap
    for record in monthly.itertuples(index=False):
        stress = 5.0 if pd.Timestamp("2023-08-01") <= record.month <= pd.Timestamp("2024-02-01") else 0.0
        dpo = float(np.clip(float(assumptions["working_capital"]["base_dpo_days"]) + stress + rng.normal(0, 1.3), 31, 48))
        target_ap = float(record.vendor_expenses_eur) * dpo / 30.4375
        payment = max(0.0, current_ap + float(record.vendor_expenses_eur) - target_ap)
        beginning_ap_values.append(current_ap)
        vendor_payments.append(payment)
        current_ap = current_ap + float(record.vendor_expenses_eur) - payment
        ap_balances.append(current_ap)
        dpo_values.append(current_ap / float(record.vendor_expenses_eur) * 30.4375)
    monthly["beginning_ap_eur"] = beginning_ap_values
    monthly["vendor_payments_eur"] = vendor_payments
    monthly["accounts_payable_eur"] = ap_balances
    monthly["dpo"] = dpo_values

    tax_payments: list[float] = []
    tax_payable_values: list[float] = []
    tax_payable = 0.0
    for record in monthly.itertuples(index=False):
        tax_payable += float(record.tax_expense_eur)
        payment = tax_payable if record.month.month in {3, 6, 9, 12} else 0.0
        tax_payable -= payment
        tax_payments.append(payment)
        tax_payable_values.append(tax_payable)
    monthly["tax_payments_eur"] = tax_payments
    monthly["tax_payable_eur"] = tax_payable_values
    monthly["operating_cash_flow_eur"] = (
        monthly["cash_collections_eur"]
        - monthly["payroll_eur"]
        - monthly["vendor_payments_eur"]
        - monthly["tax_payments_eur"]
        - monthly["interest_eur"]
    )
    monthly["free_cash_flow_eur"] = monthly["operating_cash_flow_eur"] - monthly["capex_eur"]

    opening_cash = float(assumptions["cash"]["opening_cash_eur"])
    cash_openings: list[float] = []
    financing_flows: list[float] = []
    closing_cash: list[float] = []
    current_cash = opening_cash
    yearly_net_income: dict[int, float] = {}
    for record in monthly.itertuples(index=False):
        prior_year_income = yearly_net_income.get(record.month.year - 1, 0.0)
        distribution = 0.0
        if record.month.month == int(assumptions["cash"]["annual_distribution_month"]):
            distribution = max(0.0, prior_year_income) * float(
                assumptions["cash"]["distribution_share_of_prior_year_net_income"]
            )
        financing_flow = -distribution
        cash_openings.append(current_cash)
        current_cash += float(record.free_cash_flow_eur) + financing_flow
        financing_flows.append(financing_flow)
        closing_cash.append(current_cash)
        yearly_net_income[record.month.year] = yearly_net_income.get(record.month.year, 0.0) + float(record.net_income_eur)
    monthly["opening_cash_eur"] = cash_openings
    monthly["financing_cash_flow_eur"] = financing_flows
    monthly["net_change_in_cash_eur"] = monthly["free_cash_flow_eur"] + monthly["financing_cash_flow_eur"]
    monthly["closing_cash_eur"] = closing_cash

    months_elapsed = np.arange(len(monthly), dtype=float)
    fx_noise = rng.normal(0, 0.006, len(monthly))
    fx_cycle = 0.025 * np.sin(months_elapsed / 11)
    monthly["eur_ron"] = 4.78 + 0.0032 * months_elapsed + fx_cycle + np.cumsum(fx_noise) * 0.12
    return monthly


def _generate_hiring_plan(assumptions: dict[str, Any]) -> pd.DataFrame:
    """Build the preloaded 2026 decision as level-specific monthly cohorts."""

    levels = assumptions["workforce"]["levels"]
    rate_growth_to_2026 = np.prod([1.025, 1.034, 1.046, 1.048, 1.041, 1.035])
    salary_growth_to_2026 = np.prod([1.045, 1.052, 1.078, 1.092, 1.068, 1.058, 1.05])
    monthly_totals = [7, 7, 7, 7, 6, 6]
    level_mix = np.array([0.25, 0.45, 0.225, 0.075])
    rows: list[dict[str, Any]] = []
    plan_row = 1
    for month, month_total in zip(pd.date_range("2026-01-01", periods=6, freq="MS"), monthly_totals, strict=True):
        counts = _allocate_counts(month_total, level_mix)
        for level, count in zip(LEVEL_ORDER[:4], counts, strict=True):
            if count == 0:
                continue
            config = levels[level]
            rows.append(
                {
                    "plan_id": f"HIRE-{plan_row:03d}",
                    "scenario": "2026 Expansion Decision",
                    "joining_month": month,
                    "role": "Consulting delivery",
                    "seniority": level,
                    "planned_hires": int(count),
                    "annual_base_salary_eur": float(config["annual_salary_2020_eur"]) * salary_growth_to_2026,
                    "expected_billing_rate_eur": float(config["billing_rate_2020_eur"]) * rate_growth_to_2026,
                    "expected_utilization": float(config["expected_utilization"]),
                    "ramp_up_months": 3,
                    "bonus_percent": float(config["bonus_percent"]),
                    "employer_oncost_rate": float(assumptions["workforce"]["employer_oncost_rate"]),
                    "benefits_monthly_eur": float(assumptions["workforce"]["benefits_per_employee_month_eur"]) * 1.25,
                    "recruiting_cost_per_hire_eur": 2_250.0,
                    "equipment_cost_per_hire_eur": float(assumptions["capex"]["equipment_per_new_hire_eur"]),
                    "status": "Proposed",
                }
            )
            plan_row += 1
    return pd.DataFrame(rows)


def _distribute(total: float, weights: np.ndarray) -> np.ndarray:
    weights = np.maximum(weights.astype(float), 0.0)
    if weights.sum() == 0:
        weights[-1] = 1.0
    values = total * weights / weights.sum()
    values[-1] += total - values.sum()
    return values


def _generate_weekly_cash_actuals(
    monthly: pd.DataFrame, assumptions: dict[str, Any], rng: np.random.Generator
) -> pd.DataFrame:
    """Disaggregate the latest two years into a direct weekly cash bridge."""

    rows: list[dict[str, Any]] = []
    history = monthly.loc[monthly["month"] >= pd.Timestamp("2024-01-01")]
    current_cash = float(history.iloc[0]["opening_cash_eur"])
    threshold = float(assumptions["cash"]["minimum_cash_threshold_eur"])
    for record in history.itertuples(index=False):
        month = pd.Timestamp(record.month)
        next_month = month + pd.offsets.MonthBegin(1)
        weeks = pd.date_range(month, next_month - pd.Timedelta(days=1), freq="W-MON")
        if len(weeks) == 0:
            weeks = pd.DatetimeIndex([month])
        count = len(weeks)
        collections = _distribute(float(record.cash_collections_eur), rng.gamma(3.0, 1.0, count))
        payroll_weights = np.zeros(count)
        payroll_weights[-1] = 0.92
        payroll_weights[0] += 0.08
        payroll = _distribute(float(record.payroll_eur), payroll_weights)
        vendors = _distribute(float(record.vendor_payments_eur), rng.uniform(0.7, 1.3, count))
        tax_weights = np.zeros(count)
        tax_weights[-1] = 1.0
        taxes = _distribute(float(record.tax_payments_eur), tax_weights)
        capex = _distribute(float(record.capex_eur), rng.uniform(0.5, 1.5, count))
        other_total = float(record.interest_eur) + max(0.0, -float(record.financing_cash_flow_eur))
        other = _distribute(other_total, tax_weights)
        for index, week in enumerate(weeks):
            net_cash_flow = collections[index] - payroll[index] - vendors[index] - taxes[index] - capex[index] - other[index]
            opening = current_cash
            current_cash += net_cash_flow
            rows.append(
                {
                    "week_start": week,
                    "week_end": week + pd.Timedelta(days=6),
                    "opening_cash_eur": opening,
                    "customer_collections_eur": collections[index],
                    "payroll_eur": payroll[index],
                    "vendor_payments_eur": vendors[index],
                    "tax_payments_eur": taxes[index],
                    "capex_eur": capex[index],
                    "other_scheduled_payments_eur": other[index],
                    "net_cash_flow_eur": net_cash_flow,
                    "closing_cash_eur": current_cash,
                    "minimum_cash_threshold_eur": threshold,
                    "liquidity_headroom_eur": current_cash - threshold,
                }
            )
    return pd.DataFrame(rows)


def _validate(
    datasets: dict[str, pd.DataFrame], assumptions: dict[str, Any]
) -> None:
    """Fail fast when the generated business story violates basic logic."""

    monthly = datasets["monthly_kpis"]
    invoices = datasets["invoices"]
    assert len(monthly) == 72
    assert monthly["month"].min() == pd.Timestamp("2020-01-01")
    assert monthly["month"].max() == pd.Timestamp("2025-12-01")
    assert monthly["utilization"].between(0.55, 0.90).all()
    assert monthly["billable_share"].between(0.70, 0.90).all()
    assert monthly["dso"].between(30, 90).all()
    assert monthly["headcount"].gt(0).all()
    assert monthly["billing_rate_eur"].gt(0).all()
    assert monthly["cash_collections_eur"].ge(0).all()
    expected_headcount = monthly["beginning_headcount"] + monthly["new_hires"] - monthly["attrition"]
    assert np.array_equal(monthly["headcount"].to_numpy(), expected_headcount.to_numpy())
    expected_revenue = (
        monthly["billable_hours"] * monthly["billing_rate_eur"] * monthly["realization_rate"]
        + monthly["contractor_revenue_eur"]
    )
    assert np.allclose(monthly["revenue_eur"], expected_revenue, rtol=1e-10)
    invoice_revenue = invoices.groupby(invoices["invoice_date"].dt.to_period("M"))["amount_eur"].sum()
    actual_revenue = monthly.set_index(monthly["month"].dt.to_period("M"))["revenue_eur"]
    assert np.allclose(invoice_revenue, actual_revenue, atol=0.05)
    assert np.allclose(
        monthly["beginning_ar_eur"] + monthly["revenue_eur"] - monthly["cash_collections_eur"] - monthly["writeoffs_eur"],
        monthly["accounts_receivable_eur"],
        atol=0.05,
    )
    assert np.allclose(
        monthly["opening_cash_eur"] + monthly["net_change_in_cash_eur"],
        monthly["closing_cash_eur"],
        atol=0.05,
    )
    assert len(datasets["employees"]) == int(monthly.iloc[-1]["headcount"])
    assert int(datasets["hiring_plan"]["planned_hires"].sum()) == 40
    invoice_customer_revenue = invoices.groupby("customer_id")["amount_eur"].sum().sort_values(ascending=False)
    assert invoice_customer_revenue.head(5).sum() / invoice_customer_revenue.sum() >= 0.45
    assert float(assumptions["cash"]["minimum_cash_threshold_eur"]) > 0


def _prepare_for_csv(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.select_dtypes(include=["datetime", "datetimetz"]).columns:
        output[column] = output[column].dt.strftime("%Y-%m-%d")
    return output


def _write_datasets(
    datasets: dict[str, pd.DataFrame], output_dir: Path, write_parquet: bool
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    parquet_available = bool(
        importlib.util.find_spec("pyarrow") or importlib.util.find_spec("fastparquet")
    )
    for name, frame in datasets.items():
        csv_path = output_dir / f"{name}.csv"
        _prepare_for_csv(frame).to_csv(csv_path, index=False, float_format="%.4f")
        written.append(csv_path.name)
        if write_parquet and parquet_available:
            parquet_path = output_dir / f"{name}.parquet"
            frame.to_parquet(parquet_path, index=False)
            written.append(parquet_path.name)
    return written


def generate_company(
    output_dir: str | Path | None = None,
    seed: int = SEED,
    write_parquet: bool = True,
) -> dict[str, pd.DataFrame]:
    """Generate and save all NovaPlan source datasets.

    Parameters
    ----------
    output_dir:
        Destination data directory.  Defaults to ``<project>/data``.
    seed:
        Random seed; 42 is the product default and reproduces the checked-in data.
    write_parquet:
        Also write Parquet when either pyarrow or fastparquet is already installed.
    """

    assumptions = _load_assumptions()
    rng = np.random.default_rng(seed)
    customers = _make_customers(rng)
    monthly, employees = _generate_operations(assumptions, rng)
    invoices = _generate_invoices(monthly, customers, assumptions, rng)
    opex = _generate_opex(monthly, rng)
    capex = _generate_capex(monthly, assumptions, rng)
    monthly = _complete_financials(monthly, invoices, opex, capex, assumptions, rng)
    hiring_plan = _generate_hiring_plan(assumptions)
    weekly = _generate_weekly_cash_actuals(monthly, assumptions, rng)
    datasets = {
        "monthly_kpis": monthly,
        "invoices": invoices,
        "customers": customers,
        "employees": employees,
        "hiring_plan": hiring_plan,
        "opex": opex,
        "capex": capex,
        "weekly_cash_actuals": weekly,
    }
    _validate(datasets, assumptions)
    _write_datasets(datasets, Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR, write_parquet)
    return datasets


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--no-parquet", action="store_true", help="Write CSV files only")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    datasets = generate_company(args.output_dir, args.seed, not args.no_parquet)
    print(f"NovaPlan synthetic data generated with seed {args.seed}:")
    for name, frame in datasets.items():
        print(f"  {name:24s} {len(frame):5d} rows x {len(frame.columns):2d} columns")


if __name__ == "__main__":
    main()
