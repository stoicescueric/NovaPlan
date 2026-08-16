"""Revenue driver invariants."""

from __future__ import annotations

import pytest

from models.revenue import calculate_revenue


BASE_DRIVERS = {
    "headcount": 280,
    "billable_share": 0.82,
    "working_days": 20,
    "utilization": 0.72,
    "billing_rate_eur": 62.0,
    "realization_rate": 0.97,
}


def test_increasing_utilization_increases_revenue_proportionally() -> None:
    base = calculate_revenue(**BASE_DRIVERS)
    higher = calculate_revenue(**{**BASE_DRIVERS, "utilization": 0.78})

    assert higher > base
    assert higher / base == pytest.approx(0.78 / 0.72)


def test_increasing_billing_rate_increases_revenue_proportionally() -> None:
    base = calculate_revenue(**BASE_DRIVERS)
    higher = calculate_revenue(**{**BASE_DRIVERS, "billing_rate_eur": 65.10})

    assert higher > base
    assert higher / base == pytest.approx(1.05)


def test_revenue_rejects_impossible_negative_or_fractional_inputs() -> None:
    with pytest.raises(ValueError):
        calculate_revenue(**{**BASE_DRIVERS, "headcount": -1})
    with pytest.raises(ValueError):
        calculate_revenue(**{**BASE_DRIVERS, "billable_share": 1.1})
