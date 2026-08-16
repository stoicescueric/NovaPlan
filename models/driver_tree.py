"""Transparent revenue driver tree used across NovaPlan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ._utils import validate_fraction


@dataclass(frozen=True, slots=True)
class RevenueDrivers:
    """Operational inputs for one period of services revenue.

    Monetary values are expressed in EUR. ``backlog_revenue_eur`` represents only
    work recognized in the period, not the full contracted backlog balance.
    """

    headcount: float
    billable_share: float
    working_days: float
    utilization: float
    billing_rate_eur: float
    realization_rate: float = 0.97
    hours_per_day: float = 8.0
    backlog_revenue_eur: float = 0.0
    contractor_revenue_eur: float = 0.0
    service_mix_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.headcount < 0:
            raise ValueError("headcount cannot be negative.")
        if self.working_days < 0 or self.hours_per_day <= 0:
            raise ValueError("working_days must be non-negative and hours_per_day positive.")
        if self.billing_rate_eur < 0:
            raise ValueError("billing_rate_eur cannot be negative.")
        validate_fraction("billable_share", self.billable_share)
        validate_fraction("utilization", self.utilization, upper=1.25)
        validate_fraction("realization_rate", self.realization_rate, upper=1.10)
        if self.service_mix_factor < 0:
            raise ValueError("service_mix_factor cannot be negative.")


def revenue_driver_tree(drivers: RevenueDrivers) -> dict[str, float]:
    """Calculate each visible stage in the monthly revenue driver tree."""

    capacity_hours = (
        drivers.headcount
        * drivers.billable_share
        * drivers.working_days
        * drivers.hours_per_day
    )
    billable_hours = capacity_hours * drivers.utilization
    core_revenue = (
        billable_hours
        * drivers.billing_rate_eur
        * drivers.realization_rate
        * drivers.service_mix_factor
    )
    revenue = core_revenue + drivers.backlog_revenue_eur + drivers.contractor_revenue_eur
    return {
        "billable_capacity_hours": float(capacity_hours),
        "billable_hours": float(billable_hours),
        "core_services_revenue_eur": float(core_revenue),
        "backlog_revenue_eur": float(drivers.backlog_revenue_eur),
        "contractor_revenue_eur": float(drivers.contractor_revenue_eur),
        "revenue_eur": float(revenue),
    }


def driver_tree_from_mapping(values: dict[str, Any]) -> dict[str, float]:
    """Convenience wrapper useful for configuration- or form-driven callers."""

    return revenue_driver_tree(RevenueDrivers(**values))
