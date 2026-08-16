"""Responsiveness tests for every control in the simplified student pages."""

from __future__ import annotations

import pytest

# Importing the Dash app registers all page modules before callbacks are called directly.
import app  # noqa: F401
from pages.cash_check import update_cash_check
from pages.monte_carlo import update_monte_carlo
from pages.what_if import update_what_if


def test_every_what_if_control_reaches_the_financial_model() -> None:
    base = update_what_if(0, 0, 0, 0)[3]
    hires = update_what_if(40, 0, 0, 0)[3]
    utilization = update_what_if(0, 5, 0, 0)[3]
    rate = update_what_if(0, 0, 5, 0)[3]
    slow_payment = update_what_if(0, 0, 0, 15)[3]

    assert hires["ending_headcount"] > base["ending_headcount"]
    assert utilization["revenue_change_eur"] > base["revenue_change_eur"]
    assert rate["revenue_change_eur"] > base["revenue_change_eur"]
    assert slow_payment["minimum_cash_eur"] < base["minimum_cash_eur"]
    assert slow_payment["profit_change_eur"] == pytest.approx(base["profit_change_eur"])


def test_every_cash_check_control_changes_the_weekly_plan() -> None:
    base = update_cash_check(0, 0, 0)[3]
    delay = update_cash_check(14, 0, 0)[3]
    hires = update_cash_check(0, 40, 0)[3]
    surprise = update_cash_check(0, 0, 1_000_000)[3]

    assert delay["ending_cash_eur"] < base["ending_cash_eur"]
    assert hires["ending_cash_eur"] < base["ending_cash_eur"]
    assert surprise["minimum_cash_eur"] < base["minimum_cash_eur"]
    assert surprise["ending_cash_eur"] == pytest.approx(base["ending_cash_eur"] - 1_000_000)


def test_monte_carlo_uncertainty_control_visibly_widens_the_range() -> None:
    deterministic = update_monte_carlo("base", 0, 16_000_000, 2_000)[3]
    normal = update_monte_carlo("base", 100, 16_000_000, 2_000)[3]
    high = update_monte_carlo("base", 200, 16_000_000, 2_000)[3]

    assert deterministic["range_width_eur"] == pytest.approx(0)
    assert normal["range_width_eur"] > 0
    assert high["range_width_eur"] > normal["range_width_eur"]


def test_monte_carlo_target_classifies_but_does_not_move_cash() -> None:
    low_target = update_monte_carlo("base", 100, 14_000_000, 2_000)[3]
    high_target = update_monte_carlo("base", 100, 18_000_000, 2_000)[3]

    assert high_target["probability_cash_below_threshold"] > low_target["probability_cash_below_threshold"]
    assert high_target["median_year_end_cash_eur"] == pytest.approx(low_target["median_year_end_cash_eur"])
    assert high_target["range_width_eur"] == pytest.approx(low_target["range_width_eur"])


def test_monte_carlo_plan_selector_changes_the_underlying_forecast() -> None:
    base = update_monte_carlo("base", 100, 16_000_000, 2_000)[3]
    hiring = update_monte_carlo("hire_40", 100, 16_000_000, 2_000)[3]

    assert hiring["expected_year_end_cash_eur"] != pytest.approx(base["expected_year_end_cash_eur"])
