"""Robot rental experiment: how uptime and payment delay turn profit into cash.

RoboHire SRL is a second fictional company. It buys a fleet of robot cells up
front and rents them to small manufacturers by the hour. A robot that is down
earns nothing and needs repairs, and customers pay weeks after the work is done,
so the company can report a profit while its bank balance runs low. Every
default lives in ``config/robot_rental.yaml`` and is an illustrative assumption
for a fictional company, not market data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.special import betaincinv

from ._utils import merge_options, validate_fraction
from .working_capital import AVERAGE_DAYS_PER_MONTH


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "robot_rental.yaml"


def _load_config() -> dict[str, Any]:
    """Read the illustrative RoboHire assumptions."""

    with CONFIG_PATH.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


_CONFIG = _load_config()
COMPANY_NAME: str = str(_CONFIG["company"]["name"])
DEFAULT_RENTAL_ASSUMPTIONS: dict[str, Any] = {**_CONFIG["forecast"], **_CONFIG["uncertainty"]}
DEFAULT_SWEEP_UPTIMES: tuple[float, ...] = tuple(
    float(value) for value in np.round(np.arange(0.80, 1.0001, 0.01), 2)
)

FORECAST_COLUMNS = [
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

_NON_NEGATIVE_KEYS = (
    "fleet_size",
    "robot_cost_eur",
    "deploy_per_month",
    "booked_hours_per_robot_month",
    "hourly_rate_eur",
    "repair_cost_per_down_hour_eur",
    "service_cost_per_robot_month_eur",
    "fixed_opex_month_eur",
    "dso_days",
    "uptime_path_std_pp",
    "uptime_monthly_std_pp",
    "dso_path_std_days",
    "booked_hours_path_std_pct",
)
# A Beta distribution with mean m can have a variance just below m * (1 - m).
# Capping at half of that keeps both shape parameters positive near 0% or 100%.
_MAX_BETA_VARIANCE_SHARE = 0.5
# Rounding slack (EUR) allowed when checking that lowest cash rises with uptime.
_MONOTONE_TOLERANCE_EUR = 1e-6


def _resolve(assumptions: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge overrides into the YAML defaults and reject impossible values."""

    unknown = sorted(set(assumptions or {}) - set(DEFAULT_RENTAL_ASSUMPTIONS))
    if unknown:
        raise ValueError(f"Unknown robot rental assumption(s): {', '.join(unknown)}.")
    options = merge_options(DEFAULT_RENTAL_ASSUMPTIONS, assumptions)
    for key, value in options.items():
        if not np.isfinite(float(value)):
            raise ValueError(f"{key} must be a finite number; received {value!r}.")
    if int(options["months"]) != float(options["months"]) or int(options["months"]) <= 0:
        raise ValueError("months must be a positive whole number.")
    if float(options["useful_life_months"]) <= 0:
        raise ValueError("useful_life_months must be positive.")
    for key in _NON_NEGATIVE_KEYS:
        if float(options[key]) < 0:
            raise ValueError(f"{key} cannot be negative; received {options[key]!r}.")
    validate_fraction("uptime", float(options["uptime"]))
    return options


def _collect(revenue: np.ndarray, dso_days: np.ndarray) -> np.ndarray:
    """Move earned revenue into the months in which customers actually pay.

    A delay of ``d`` months is ``k`` whole months plus a fraction ``f``. Revenue
    earned in month ``s`` is collected ``1 - f`` in month ``s + k`` and ``f`` in
    month ``s + k + 1``, so the average delay is exactly ``d``. Anything due
    after the last month is never collected inside the horizon.
    """

    delay = np.asarray(dso_days, dtype=float) / AVERAGE_DAYS_PER_MONTH
    whole = np.floor(delay)
    fraction = delay - whole
    months = revenue.shape[1]
    source = np.arange(months)[None, :] - whole.astype(int)

    def earned_in(month_index: np.ndarray) -> np.ndarray:
        values = np.take_along_axis(revenue, np.clip(month_index, 0, months - 1), axis=1)
        return np.where(month_index >= 0, values, 0.0)

    return (1.0 - fraction) * earned_in(source) + fraction * earned_in(source - 1)


def _simulate(
    options: Mapping[str, Any],
    uptime: np.ndarray,
    dso_days: np.ndarray,
    booked_hours_factor: np.ndarray,
) -> dict[str, np.ndarray]:
    """Run the monthly mechanics for one or many paths.

    ``uptime`` has shape (paths, months); ``dso_days`` and
    ``booked_hours_factor`` have shape (paths, 1). The deterministic forecast
    and every Monte Carlo path go through this single function.
    """

    months = int(options["months"])
    fleet_size = float(options["fleet_size"])
    month_index = np.arange(months)

    placed = np.minimum(fleet_size, float(options["deploy_per_month"]) * (month_index + 1))[None, :]
    booked_hours = placed * float(options["booked_hours_per_robot_month"]) * booked_hours_factor
    working_hours = booked_hours * uptime
    downtime_hours = booked_hours * (1.0 - uptime)

    revenue = working_hours * float(options["hourly_rate_eur"])
    cash_costs = (
        downtime_hours * float(options["repair_cost_per_down_hour_eur"])
        + placed * float(options["service_cost_per_robot_month_eur"])
        + float(options["fixed_opex_month_eur"])
    )
    fleet_cost = fleet_size * float(options["robot_cost_eur"])
    monthly_depreciation = fleet_cost / float(options["useful_life_months"])
    # Straight line, stopping once the robots are fully depreciated.
    depreciation = np.clip(fleet_cost - monthly_depreciation * month_index, 0.0, monthly_depreciation)[None, :]
    operating_profit = revenue - cash_costs - depreciation

    collections = _collect(revenue, dso_days)
    capex = np.zeros(months)
    capex[0] = fleet_cost
    closing_cash = float(options["opening_cash_eur"]) + np.cumsum(collections - cash_costs - capex, axis=1)

    shape = revenue.shape
    return {
        "placed_robots": np.broadcast_to(placed, shape),
        "working_hours": working_hours,
        "downtime_hours": downtime_hours,
        "revenue_eur": revenue,
        "cash_costs_eur": cash_costs,
        "depreciation_eur": np.broadcast_to(depreciation, shape),
        "operating_profit_eur": operating_profit,
        "cumulative_profit_eur": np.cumsum(operating_profit, axis=1),
        "collections_eur": collections,
        "receivables_eur": np.cumsum(revenue - collections, axis=1),
        "closing_cash_eur": closing_cash,
    }


def _deterministic(options: Mapping[str, Any]) -> dict[str, np.ndarray]:
    months = int(options["months"])
    return _simulate(
        options,
        uptime=np.full((1, months), float(options["uptime"])),
        dso_days=np.full((1, 1), float(options["dso_days"])),
        booked_hours_factor=np.ones((1, 1)),
    )


def build_rental_forecast(assumptions: Mapping[str, Any] | None = None) -> pd.DataFrame:
    """Deterministic monthly forecast.

    Month 0 is the month the robots are bought. Simplifications: the whole fleet
    is paid for in month 0 (no financing), placed robots ramp up by
    ``deploy_per_month``, revenue is earned on working hours only, cash costs
    are paid in the month they occur, depreciation is straight-line over
    ``useful_life_months``, and there is no tax, VAT or interest. Revenue still
    unpaid at the end of the horizon stays in receivables; it is not cash.
    """

    options = _resolve(assumptions)
    paths = _deterministic(options)
    frame = pd.DataFrame({"month": np.arange(int(options["months"]))})
    for column in FORECAST_COLUMNS[1:]:
        frame[column] = paths[column][0]
    return frame


def _beta_quantile(mean: float, std: float, luck: np.ndarray) -> np.ndarray:
    """Turn uniform luck into draws from a Beta distribution with this mean and std."""

    variance = min(std**2, _MAX_BETA_VARIANCE_SHARE * mean * (1.0 - mean))
    if variance <= 0.0:
        return np.full(luck.shape, mean)
    concentration = mean * (1.0 - mean) / variance - 1.0
    return betaincinv(mean * concentration, (1.0 - mean) * concentration, luck)


def _draw_luck(n_simulations: int, months: int, seed: int) -> dict[str, np.ndarray]:
    """Draw every random number up front, in a fixed order.

    The same seed therefore gives each run the same luck at any uptime or
    uncertainty level, which keeps comparisons between settings fair.
    """

    rng = np.random.default_rng(seed)
    return {
        "uptime": rng.random(n_simulations),
        "uptime_monthly": rng.standard_normal((n_simulations, months)),
        "dso": rng.standard_normal(n_simulations),
        "booked_hours": rng.standard_normal(n_simulations),
    }


def _simulate_paths(
    options: Mapping[str, Any],
    luck: Mapping[str, np.ndarray],
    uncertainty_scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Turn luck into drivers and return (closing cash, cumulative profit) paths."""

    path_uptime = _beta_quantile(
        float(options["uptime"]),
        uncertainty_scale * float(options["uptime_path_std_pp"]),
        luck["uptime"],
    )
    uptime = np.clip(
        path_uptime[:, None]
        + uncertainty_scale * float(options["uptime_monthly_std_pp"]) * luck["uptime_monthly"],
        0.0,
        1.0,
    )
    dso_days = np.maximum(
        float(options["dso_days"]) + uncertainty_scale * float(options["dso_path_std_days"]) * luck["dso"],
        0.0,
    )[:, None]
    booked_hours_factor = np.maximum(
        1.0 + uncertainty_scale * float(options["booked_hours_path_std_pct"]) * luck["booked_hours"],
        0.0,
    )[:, None]
    paths = _simulate(options, uptime, dso_days, booked_hours_factor)
    return paths["closing_cash_eur"], paths["cumulative_profit_eur"]


def _breach_statistics(cash: np.ndarray, profit: np.ndarray, floor: float) -> dict[str, Any]:
    """Count paths that fall below the floor and those still profitable when they do."""

    below = cash < floor
    breached = below.any(axis=1)
    first_breach = below.argmax(axis=1)
    profit_at_breach = profit[np.arange(len(profit)), first_breach]
    profitable_but_broke = breached & (profit_at_breach > 0.0)
    breach_count = int(breached.sum())
    profitable_count = int(profitable_but_broke.sum())
    return {
        "breach_probability": breach_count / len(cash),
        # Undefined (NaN) when no path breaches: there is nothing to take a share of.
        "profitable_but_broke_share": profitable_count / breach_count if breach_count else float("nan"),
        "first_breach_month": first_breach[breached],
        "breach_count": breach_count,
        "profitable_but_broke_count": profitable_count,
    }


def _validate_simulation(n_simulations: int, uncertainty_scale: float) -> float:
    if int(n_simulations) <= 0:
        raise ValueError("n_simulations must be positive.")
    scale = float(uncertainty_scale)
    if not np.isfinite(scale) or scale < 0:
        raise ValueError("uncertainty_scale must be a finite non-negative number.")
    return scale


def run_rental_monte_carlo(
    assumptions: Mapping[str, Any] | None = None,
    n_simulations: int = 5_000,
    seed: int = 42,
    uncertainty_scale: float = 1.0,
) -> dict[str, Any]:
    """Vectorized Monte Carlo over uptime, DSO and booked hours.

    Each run draws its luck once and keeps it for the whole horizon: an average
    uptime from a Beta distribution centred on ``uptime``, a payment delay from
    a normal distribution around ``dso_days`` (at least 0) and a booked-hours
    multiplier around 1.0 (at least 0). Uptime also wobbles from month to
    month and is clipped to [0, 1]. Every spread is multiplied by
    ``uncertainty_scale``, and the drivers flow through exactly the same monthly
    mechanics as ``build_rental_forecast``, so at ``uncertainty_scale=0`` every
    run equals the deterministic forecast.

    ``profitable_but_broke_share`` is the share of breaching runs whose
    cumulative operating profit is positive in the month cash first drops below
    the floor; it is NaN when no run breaches.
    """

    scale = _validate_simulation(n_simulations, uncertainty_scale)
    options = _resolve(assumptions)
    months = int(options["months"])
    luck = _draw_luck(int(n_simulations), months, seed)
    cash, profit = _simulate_paths(options, luck, scale)
    statistics = _breach_statistics(cash, profit, float(options["cash_floor_eur"]))
    p5, p50, p95 = np.percentile(cash, [5, 50, 95], axis=0)
    percentiles = pd.DataFrame(
        {"month": np.arange(months), "p5_cash_eur": p5, "p50_cash_eur": p50, "p95_cash_eur": p95}
    )
    return {
        "cash_paths": cash,
        "profit_paths": profit,
        "percentiles": percentiles,
        **statistics,
        "n_simulations": int(n_simulations),
        "seed": int(seed),
        "uncertainty_scale": scale,
        "inputs": dict(options),
    }


def find_uptime_threshold(
    assumptions: Mapping[str, Any] | None = None,
    lower: float = 0.50,
    upper: float = 1.00,
    tol: float = 1e-4,
) -> float | None:
    """Lowest uptime at which the deterministic forecast never drops below cash_floor_eur.

    Bisection is valid because more uptime means more revenue and less repair
    cost in every month, so the lowest cash balance can only rise with uptime;
    every step checks that this still holds. Returns None if even ``upper``
    (100% by default) breaches the floor and ``lower`` if every uptime in the
    range is safe. Otherwise the result is safe and at most ``tol`` above the
    exact threshold.
    """

    if not 0.0 <= lower < upper <= 1.0:
        raise ValueError("Need 0 <= lower < upper <= 1.")
    if tol <= 0:
        raise ValueError("tol must be positive.")
    options = _resolve(assumptions)
    floor = float(options["cash_floor_eur"])

    def lowest_cash(uptime: float) -> float:
        return float(_deterministic({**options, "uptime": uptime})["closing_cash_eur"].min())

    low, high = float(lower), float(upper)
    low_cash, high_cash = lowest_cash(low), lowest_cash(high)
    if low_cash > high_cash + _MONOTONE_TOLERANCE_EUR:
        raise ValueError("Lowest cash fell as uptime rose; bisection would be unreliable.")
    if high_cash < floor:
        return None
    if low_cash >= floor:
        return low
    while high - low > tol:
        middle = 0.5 * (low + high)
        middle_cash = lowest_cash(middle)
        if not low_cash - _MONOTONE_TOLERANCE_EUR <= middle_cash <= high_cash + _MONOTONE_TOLERANCE_EUR:
            raise ValueError("Lowest cash is not monotone in uptime; bisection would be unreliable.")
        if middle_cash >= floor:
            high, high_cash = middle, middle_cash
        else:
            low, low_cash = middle, middle_cash
    return high


def uptime_sweep(
    assumptions: Mapping[str, Any] | None = None,
    uptimes: Sequence[float] = DEFAULT_SWEEP_UPTIMES,
    n_simulations: int = 2_000,
    seed: int = 42,
    uncertainty_scale: float = 1.0,
) -> pd.DataFrame:
    """For each mean uptime: breach probability, and the share of breaching
    paths whose cumulative operating profit was positive at the breach month.

    Every uptime reuses the same random luck, so differences between rows come
    from uptime alone rather than from a fresh set of random draws.
    """

    scale = _validate_simulation(n_simulations, uncertainty_scale)
    options = _resolve(assumptions)
    luck = _draw_luck(int(n_simulations), int(options["months"]), seed)
    rows = []
    for uptime in uptimes:
        uptime_options = _resolve({**dict(assumptions or {}), "uptime": float(uptime)})
        cash, profit = _simulate_paths(uptime_options, luck, scale)
        statistics = _breach_statistics(cash, profit, float(uptime_options["cash_floor_eur"]))
        rows.append(
            {
                "uptime": float(uptime),
                "breach_probability": statistics["breach_probability"],
                "profitable_but_broke_share": statistics["profitable_but_broke_share"],
                "breach_count": statistics["breach_count"],
                "profitable_but_broke_count": statistics["profitable_but_broke_count"],
            }
        )
    return pd.DataFrame(rows)
