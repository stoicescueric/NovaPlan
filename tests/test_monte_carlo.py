"""Monte Carlo propagation and reproducibility tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.monte_carlo import run_monte_carlo


def _history() -> pd.DataFrame:
    periods = 24
    position = np.arange(periods)
    frame = pd.DataFrame(
        {
            "month": pd.date_range("2024-01-01", periods=periods, freq="MS"),
            "headcount": 280 + position,
            "new_hires": [4.0] * periods,
            "attrition": [2.0] * periods,
            "billable_share": [0.82] * periods,
            "utilization": 0.74 + 0.03 * np.sin(position * 2 * np.pi / 12),
            "working_days": [21] * periods,
            "billing_rate_eur": 62 + position * 0.10,
            "realization_rate": [0.97] * periods,
            "payroll_eur": [850_000.0] * periods,
            "contractor_cost_eur": [140_000.0] * periods,
            "other_opex_eur": [260_000.0] * periods,
            "capex_eur": [40_000.0] * periods,
            "depreciation_eur": [28_000.0] * periods,
            "dso": [55.0] * periods,
            "dpo": [35.0] * periods,
            "accounts_receivable_eur": [2_500_000.0] * periods,
            "accounts_payable_eur": [480_000.0] * periods,
            "closing_cash_eur": [5_500_000.0] * periods,
            "eur_ron": [4.97] * periods,
        }
    )
    frame["revenue_eur"] = (
        frame["headcount"]
        * frame["billable_share"]
        * frame["working_days"]
        * 8
        * frame["utilization"]
        * frame["billing_rate_eur"]
        * frame["realization_rate"]
    )
    return frame


def test_same_seed_reproduces_same_simulation() -> None:
    first = run_monte_carlo(_history(), n_simulations=300, seed=42, assumptions={"months": 6})
    second = run_monte_carlo(_history(), n_simulations=300, seed=42, assumptions={"months": 6})

    np.testing.assert_array_equal(first["year_end_cash_eur"], second["year_end_cash_eur"])
    np.testing.assert_array_equal(first["cash_trajectories_eur"], second["cash_trajectories_eur"])
    pd.testing.assert_frame_equal(first["fan_chart"], second["fan_chart"])
    assert first["summary"] == second["summary"]


def test_different_seed_changes_driver_propagated_outcomes() -> None:
    first = run_monte_carlo(_history(), n_simulations=200, seed=42, assumptions={"months": 6})
    second = run_monte_carlo(_history(), n_simulations=200, seed=43, assumptions={"months": 6})

    assert not np.array_equal(first["year_end_cash_eur"], second["year_end_cash_eur"])
    assert np.std(first["year_end_cash_eur"]) > 0


def test_percentiles_and_probabilities_are_ordered_and_bounded() -> None:
    result = run_monte_carlo(_history(), n_simulations=400, seed=7, assumptions={"months": 6})
    summary = result["summary"]

    percentiles = [
        summary["p5_year_end_cash_eur"],
        summary["p25_year_end_cash_eur"],
        summary["median_year_end_cash_eur"],
        summary["p75_year_end_cash_eur"],
        summary["p95_year_end_cash_eur"],
    ]
    assert percentiles == sorted(percentiles)
    for key in (
        "probability_cash_below_threshold",
        "probability_external_funding_required",
        "probability_ebitda_margin_below_target",
    ):
        assert 0 <= summary[key] <= 1
    fan = result["fan_chart"]
    assert (fan["p5_cash_eur"] <= fan["p25_cash_eur"]).all()
    assert (fan["p25_cash_eur"] <= fan["p50_cash_eur"]).all()
    assert (fan["p50_cash_eur"] <= fan["p75_cash_eur"]).all()
    assert (fan["p75_cash_eur"] <= fan["p95_cash_eur"]).all()


def test_zero_uncertainty_collapses_every_run_to_one_path() -> None:
    result = run_monte_carlo(
        _history(),
        n_simulations=300,
        seed=42,
        assumptions={"months": 6, "uncertainty_scale": 0.0},
    )

    assert np.ptp(result["year_end_cash_eur"]) == 0
    fan = result["fan_chart"]
    np.testing.assert_allclose(fan["p5_cash_eur"], fan["p95_cash_eur"])
    assert result["summary"]["uncertainty_scale"] == 0.0


def test_higher_uncertainty_widens_the_cash_range() -> None:
    low = run_monte_carlo(
        _history(),
        n_simulations=1_500,
        seed=42,
        assumptions={"months": 6, "uncertainty_scale": 0.5},
    )
    high = run_monte_carlo(
        _history(),
        n_simulations=1_500,
        seed=42,
        assumptions={"months": 6, "uncertainty_scale": 2.0},
    )

    low_width = low["summary"]["p95_year_end_cash_eur"] - low["summary"]["p5_year_end_cash_eur"]
    high_width = high["summary"]["p95_year_end_cash_eur"] - high["summary"]["p5_year_end_cash_eur"]
    assert high_width > low_width


def test_cash_target_reclassifies_the_same_simulated_paths() -> None:
    first = run_monte_carlo(
        _history(),
        n_simulations=700,
        seed=11,
        threshold=-1_000_000_000,
        assumptions={"months": 6},
    )
    useful_target = float(np.median(first["minimum_cash_eur"]))
    second = run_monte_carlo(
        _history(),
        n_simulations=700,
        seed=11,
        threshold=useful_target,
        assumptions={"months": 6},
    )

    np.testing.assert_array_equal(first["cash_trajectories_eur"], second["cash_trajectories_eur"])
    assert first["summary"]["probability_cash_below_threshold"] == 0.0
    assert 0.40 < second["summary"]["probability_cash_below_threshold"] < 0.60


def test_forecast_overrides_reach_the_simulation() -> None:
    base = run_monte_carlo(
        _history(),
        n_simulations=600,
        seed=9,
        assumptions={"months": 6},
    )
    slow_collections = run_monte_carlo(
        _history(),
        n_simulations=600,
        seed=9,
        assumptions={"months": 6, "forecast_overrides": {"dso_delta_days": 20}},
    )

    assert slow_collections["summary"]["expected_year_end_cash_eur"] < base["summary"]["expected_year_end_cash_eur"]


def test_zero_margin_target_is_not_replaced_by_the_default() -> None:
    result = run_monte_carlo(
        _history(),
        n_simulations=200,
        seed=3,
        assumptions={"months": 6, "ebitda_margin_target": 0.0},
    )

    assert result["summary"]["ebitda_margin_target"] == 0.0


def test_external_funding_need_and_safety_target_shortfall_have_clear_meanings() -> None:
    result = run_monte_carlo(
        _history(),
        n_simulations=50,
        seed=3,
        threshold=3_000_000,
        assumptions={
            "months": 1,
            "uncertainty_scale": 0.0,
            "forecast_overrides": {"opening_cash_eur": -20_000_000},
        },
    )
    summary = result["summary"]

    assert summary["probability_external_funding_required"] == 1.0
    assert summary["expected_maximum_funding_need_eur"] > 0
    assert summary["expected_shortfall_to_threshold_eur"] > summary["expected_maximum_funding_need_eur"]
