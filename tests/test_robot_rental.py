"""Behaviour tests for the robot rental experiment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Importing the Dash app registers all page modules before callbacks are called directly.
import app  # noqa: F401
from models.robot_rental import (
    DEFAULT_RENTAL_ASSUMPTIONS,
    build_rental_forecast,
    find_uptime_threshold,
    run_rental_monte_carlo,
    uptime_sweep,
)
from pages.robot_rental import layout, update_robot_rental


# A pinned copy of the illustrative defaults, so these tests keep checking the
# mechanics after the YAML numbers are replaced with sourced values.
BASE = {
    "months": 36,
    "opening_cash_eur": 600_000,
    "fleet_size": 10,
    "robot_cost_eur": 45_000,
    "deploy_per_month": 2,
    "useful_life_months": 60,
    "booked_hours_per_robot_month": 320,
    "hourly_rate_eur": 22,
    "uptime": 0.95,
    "repair_cost_per_down_hour_eur": 40,
    "service_cost_per_robot_month_eur": 450,
    "fixed_opex_month_eur": 9_000,
    "dso_days": 45,
    "cash_floor_eur": 50_000,
    "uptime_path_std_pp": 0.02,
    "uptime_monthly_std_pp": 0.01,
    "dso_path_std_days": 8,
    "booked_hours_path_std_pct": 0.08,
}
FLOOR = BASE["cash_floor_eur"]


def _forecast(**changes) -> pd.DataFrame:
    return build_rental_forecast({**BASE, **changes})


def _lowest_cash(**changes) -> float:
    return float(_forecast(**changes)["closing_cash_eur"].min())


def test_yaml_defaults_cover_every_pinned_assumption() -> None:
    assert set(DEFAULT_RENTAL_ASSUMPTIONS) == set(BASE)
    with pytest.raises(ValueError, match="Unknown"):
        build_rental_forecast({"fleet": 12})


def test_forecast_has_the_promised_columns_and_reconciles() -> None:
    forecast = _forecast()

    assert list(forecast.columns) == [
        "month",
        "placed_robots",
        "working_hours",
        "downtime_hours",
        "revenue_eur",
        "cash_costs_eur",
        "depreciation_eur",
        "operating_profit_eur",
        "cumulative_profit_eur",
        "collections_eur",
        "receivables_eur",
        "closing_cash_eur",
    ]
    assert len(forecast) == 36
    assert forecast["placed_robots"].tolist()[:6] == [2, 4, 6, 8, 10, 10]
    capex = BASE["fleet_size"] * BASE["robot_cost_eur"]
    net_cash = (forecast["collections_eur"] - forecast["cash_costs_eur"]).cumsum()
    np.testing.assert_allclose(forecast["closing_cash_eur"], BASE["opening_cash_eur"] - capex + net_cash)
    np.testing.assert_allclose(
        forecast["receivables_eur"],
        (forecast["revenue_eur"] - forecast["collections_eur"]).cumsum(),
    )
    # Revenue still unpaid at the end of the horizon stays in receivables, not cash.
    assert forecast["receivables_eur"].iloc[-1] > 0
    assert forecast["collections_eur"].sum() + forecast["receivables_eur"].iloc[-1] == pytest.approx(
        forecast["revenue_eur"].sum()
    )


def test_zero_uncertainty_reproduces_the_deterministic_forecast_exactly() -> None:
    forecast = _forecast()
    result = run_rental_monte_carlo(BASE, n_simulations=200, seed=7, uncertainty_scale=0.0)
    shape = result["cash_paths"].shape

    np.testing.assert_array_equal(
        result["cash_paths"], np.broadcast_to(forecast["closing_cash_eur"].to_numpy(), shape)
    )
    np.testing.assert_array_equal(
        result["profit_paths"], np.broadcast_to(forecast["cumulative_profit_eur"].to_numpy(), shape)
    )
    np.testing.assert_array_equal(result["percentiles"]["p5_cash_eur"], result["percentiles"]["p95_cash_eur"])


def test_same_seed_reproduces_paths_and_a_different_seed_changes_them() -> None:
    first = run_rental_monte_carlo(BASE, n_simulations=300, seed=42)
    second = run_rental_monte_carlo(BASE, n_simulations=300, seed=42)
    other = run_rental_monte_carlo(BASE, n_simulations=300, seed=43)

    np.testing.assert_array_equal(first["cash_paths"], second["cash_paths"])
    np.testing.assert_array_equal(first["profit_paths"], second["profit_paths"])
    pd.testing.assert_frame_equal(first["percentiles"], second["percentiles"])
    assert not np.array_equal(first["cash_paths"], other["cash_paths"])
    assert np.std(first["cash_paths"][:, -1]) > 0


def test_higher_uptime_gives_higher_minimum_cash() -> None:
    minimum_cash = [_lowest_cash(uptime=float(uptime)) for uptime in np.linspace(0.50, 1.00, 26)]

    assert np.all(np.diff(minimum_cash) > 0)


def test_longer_payment_delay_lowers_early_cash_but_not_revenue_or_profit() -> None:
    prompt = _forecast(dso_days=30)
    slow = _forecast(dso_days=90)

    assert (slow["closing_cash_eur"] <= prompt["closing_cash_eur"]).all()
    assert (slow["closing_cash_eur"].iloc[:6] < prompt["closing_cash_eur"].iloc[:6]).all()
    pd.testing.assert_series_equal(slow["revenue_eur"], prompt["revenue_eur"])
    pd.testing.assert_series_equal(slow["operating_profit_eur"], prompt["operating_profit_eur"])
    # The missing cash is exactly the extra money customers still owe.
    cash_gap = prompt["closing_cash_eur"].iloc[-1] - slow["closing_cash_eur"].iloc[-1]
    receivables_gap = slow["receivables_eur"].iloc[-1] - prompt["receivables_eur"].iloc[-1]
    assert cash_gap == pytest.approx(receivables_gap)


def test_robot_purchase_hits_month_zero_cash_but_profit_only_through_depreciation() -> None:
    fleet_size, robot_cost, life = BASE["fleet_size"], BASE["robot_cost_eur"], BASE["useful_life_months"]
    paid = _forecast()
    free = _forecast(robot_cost_eur=0)

    cash_gap = free["closing_cash_eur"] - paid["closing_cash_eur"]
    assert cash_gap.iloc[0] == pytest.approx(fleet_size * robot_cost)
    np.testing.assert_allclose(cash_gap, fleet_size * robot_cost)  # one-off, so the gap never grows
    profit_gap = free["operating_profit_eur"] - paid["operating_profit_eur"]
    np.testing.assert_allclose(profit_gap, fleet_size * robot_cost / life)
    np.testing.assert_allclose(paid["depreciation_eur"], fleet_size * robot_cost / life)
    for column in ("revenue_eur", "cash_costs_eur", "collections_eur"):
        pd.testing.assert_series_equal(paid[column], free[column])


def test_depreciation_stops_once_the_robots_are_written_off() -> None:
    forecast = _forecast(useful_life_months=24)
    fleet_cost = BASE["fleet_size"] * BASE["robot_cost_eur"]

    np.testing.assert_allclose(forecast["depreciation_eur"].iloc[:24], fleet_cost / 24)
    assert (forecast["depreciation_eur"].iloc[24:] == 0).all()
    assert forecast["depreciation_eur"].sum() == pytest.approx(fleet_cost)


def test_downtime_earns_no_revenue_and_adds_repair_cost() -> None:
    full = _forecast(uptime=1.0)
    partial = _forecast(uptime=0.9)

    pd.testing.assert_series_equal(partial["placed_robots"], full["placed_robots"])
    # Exact up to floating-point rounding.
    np.testing.assert_allclose(partial["revenue_eur"], 0.9 / 1.0 * full["revenue_eur"], rtol=1e-12)
    assert (full["downtime_hours"] == 0).all()
    np.testing.assert_allclose(
        partial["cash_costs_eur"] - full["cash_costs_eur"],
        partial["downtime_hours"] * BASE["repair_cost_per_down_hour_eur"],
    )
    np.testing.assert_allclose(partial["working_hours"] + partial["downtime_hours"], full["working_hours"])


@pytest.mark.parametrize("changes", [{}, {"dso_days": 90}, {"hourly_rate_eur": 18}])
def test_uptime_threshold_is_safe_and_just_above_the_breach_point(changes: dict) -> None:
    threshold = find_uptime_threshold({**BASE, **changes})

    assert threshold is not None and 0.50 < threshold < 1.00
    assert _lowest_cash(**changes, uptime=threshold) >= FLOOR
    assert _lowest_cash(**changes, uptime=threshold - 0.001) < FLOOR


def test_uptime_threshold_reports_impossible_and_always_safe_cases() -> None:
    # Buying the robots alone takes cash below the floor, whatever the uptime.
    assert find_uptime_threshold({**BASE, "opening_cash_eur": 400_000}) is None
    # So much cash that even 50% uptime never touches the floor.
    assert find_uptime_threshold({**BASE, "opening_cash_eur": 3_000_000}) == 0.50


def test_running_short_while_still_profitable_is_flagged() -> None:
    # Customers pay after about three months and little cash is left after buying the robots.
    case = {**BASE, "dso_days": 90, "opening_cash_eur": 540_000}
    forecast = build_rental_forecast(case)
    below = forecast["closing_cash_eur"] < FLOOR
    first_breach = int(below.idxmax())
    assert below.any()
    assert forecast.loc[first_breach, "cumulative_profit_eur"] > 0

    result = run_rental_monte_carlo(case, n_simulations=100, uncertainty_scale=0.0)
    assert result["breach_probability"] == 1.0
    assert result["profitable_but_broke_share"] == 1.0
    np.testing.assert_array_equal(result["first_breach_month"], first_breach)

    # Too little cash from day one: short of cash, but not yet profitable, so not flagged.
    early = run_rental_monte_carlo({**BASE, "opening_cash_eur": 500_000}, n_simulations=100, uncertainty_scale=0.0)
    assert early["breach_probability"] == 1.0
    assert early["profitable_but_broke_share"] == 0.0


def test_no_breach_leaves_the_profitable_share_undefined() -> None:
    result = run_rental_monte_carlo({**BASE, "opening_cash_eur": 3_000_000}, n_simulations=200)

    assert result["breach_probability"] == 0.0
    assert result["first_breach_month"].size == 0
    assert np.isnan(result["profitable_but_broke_share"])


def test_higher_uncertainty_widens_the_cash_range() -> None:
    low = run_rental_monte_carlo(BASE, n_simulations=2_000, seed=42, uncertainty_scale=0.5)
    high = run_rental_monte_carlo(BASE, n_simulations=2_000, seed=42, uncertainty_scale=2.0)

    def width(result: dict) -> np.ndarray:
        return (result["percentiles"]["p95_cash_eur"] - result["percentiles"]["p5_cash_eur"]).to_numpy()

    assert width(high)[-1] > width(low)[-1]
    assert width(high).mean() > width(low).mean()


def test_uptime_sweep_is_bounded_and_risk_falls_as_uptime_rises() -> None:
    sweep = uptime_sweep(
        {**BASE, "dso_days": 90, "opening_cash_eur": 550_000},
        uptimes=(0.80, 0.85, 0.90, 0.95, 1.00),
        n_simulations=500,
    )

    assert sweep["uptime"].tolist() == [0.80, 0.85, 0.90, 0.95, 1.00]
    assert sweep["breach_probability"].between(0, 1).all()
    assert (np.diff(sweep["breach_probability"]) <= 0).all()
    breached = sweep["breach_count"] > 0
    assert sweep.loc[breached, "profitable_but_broke_share"].between(0, 1).all()
    assert sweep.loc[~breached, "profitable_but_broke_share"].isna().all()


def test_robot_rental_page_builds_and_its_controls_reach_the_model() -> None:
    assert layout() is not None
    fan, sweep, kpis, _, base = update_robot_rental(10, 45_000, 22, 95, 45, 600_000, 100)
    slow_payment = update_robot_rental(10, 45_000, 22, 95, 90, 600_000, 100)[-1]
    lower_uptime = update_robot_rental(10, 45_000, 22, 85, 45, 600_000, 100)[-1]
    no_wobble = update_robot_rental(10, 45_000, 22, 95, 45, 600_000, 0)[-1]

    assert len(fan.data) == 4 and len(kpis) == 3
    assert {"Chance of running short of cash", "Of those runs, still profitable"} <= {trace.name for trace in sweep.data}
    assert slow_payment["ending_cash_eur"] < base["ending_cash_eur"]
    assert slow_payment["minimum_cash_eur"] <= base["minimum_cash_eur"]
    assert slow_payment["total_operating_profit_eur"] == pytest.approx(base["total_operating_profit_eur"])
    assert lower_uptime["total_revenue_eur"] < base["total_revenue_eur"]
    assert lower_uptime["lowest_safe_uptime"] == base["lowest_safe_uptime"]
    assert no_wobble["range_width_eur"] == pytest.approx(0)
    assert base["range_width_eur"] > 0
