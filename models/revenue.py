"""Revenue calculations built on the explicit operational driver tree."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ._utils import merge_options
from .driver_tree import RevenueDrivers, revenue_driver_tree


DEFAULT_REVENUE_ASSUMPTIONS: dict[str, float] = {
    "hours_per_day": 8.0,
    "realization_rate": 0.97,
    "backlog_conversion_rate": 0.0,
    "service_mix_factor": 1.0,
}


def calculate_revenue(
    headcount: float,
    billable_share: float,
    working_days: float,
    utilization: float,
    billing_rate_eur: float,
    realization_rate: float = 0.97,
    hours_per_day: float = 8.0,
    backlog_revenue_eur: float = 0.0,
    contractor_revenue_eur: float = 0.0,
    service_mix_factor: float = 1.0,
) -> float:
    """Calculate recognized services revenue for a single period."""

    drivers = RevenueDrivers(
        headcount=headcount,
        billable_share=billable_share,
        working_days=working_days,
        utilization=utilization,
        billing_rate_eur=billing_rate_eur,
        realization_rate=realization_rate,
        hours_per_day=hours_per_day,
        backlog_revenue_eur=backlog_revenue_eur,
        contractor_revenue_eur=contractor_revenue_eur,
        service_mix_factor=service_mix_factor,
    )
    return revenue_driver_tree(drivers)["revenue_eur"]


def build_revenue_schedule(
    drivers: pd.DataFrame,
    assumptions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Apply the driver tree to every row of a monthly driver dataframe.

    Required columns are ``headcount``, ``billable_share``, ``working_days``,
    ``utilization`` and ``billing_rate_eur``. Optional row-level columns override
    the corresponding assumptions.
    """

    required = {
        "headcount",
        "billable_share",
        "working_days",
        "utilization",
        "billing_rate_eur",
    }
    missing = required.difference(drivers.columns)
    if missing:
        raise ValueError(f"Missing revenue drivers: {', '.join(sorted(missing))}.")

    options = merge_options(DEFAULT_REVENUE_ASSUMPTIONS, assumptions)
    result = drivers.copy()

    def values(column: str, fallback: float) -> np.ndarray:
        if column in result:
            return pd.to_numeric(result[column], errors="coerce").fillna(fallback).to_numpy(float)
        return np.full(len(result), float(fallback))

    headcount = values("revenue_headcount", 0.0) if "revenue_headcount" in result else values("headcount", 0.0)
    capacity = (
        headcount
        * values("billable_share", 0.0)
        * values("working_days", 0.0)
        * values("hours_per_day", float(options["hours_per_day"]))
    )
    billable_hours = capacity * values("utilization", 0.0)
    core_revenue = (
        billable_hours
        * values("billing_rate_eur", 0.0)
        * values("realization_rate", float(options["realization_rate"]))
        * values("service_mix_factor", float(options["service_mix_factor"]))
    )

    backlog_balance = values("backlog_eur", 0.0)
    backlog_revenue = values(
        "backlog_revenue_eur",
        0.0,
    )
    if "backlog_revenue_eur" not in result:
        backlog_revenue = backlog_balance * float(options["backlog_conversion_rate"])
    contractor_revenue = values("contractor_revenue_eur", 0.0)

    result["billable_capacity_hours"] = capacity
    result["billable_hours"] = billable_hours
    result["core_services_revenue_eur"] = core_revenue
    result["backlog_revenue_recognized_eur"] = backlog_revenue
    result["revenue_eur"] = core_revenue + backlog_revenue + contractor_revenue
    return result


# Friendly alias for callers that use "forecast" terminology.
revenue_from_drivers = build_revenue_schedule
