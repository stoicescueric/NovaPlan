"""Traceable, rule-based management observations."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .forecast import build_monthly_forecast
from .sensitivity import run_sensitivity


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    amount = abs(float(value))
    if amount >= 1_000_000:
        return f"{sign}EUR {amount / 1_000_000:.1f}m"
    if amount >= 1_000:
        return f"{sign}EUR {amount / 1_000:.0f}k"
    return f"{sign}EUR {amount:,.0f}"


def _scenario_frame(scenario_results: Any) -> pd.DataFrame | None:
    if isinstance(scenario_results, pd.DataFrame):
        return scenario_results
    if isinstance(scenario_results, dict):
        if isinstance(scenario_results.get("comparison"), pd.DataFrame):
            return scenario_results["comparison"]
        if isinstance(scenario_results.get("summary"), dict):
            return pd.DataFrame([scenario_results["summary"]])
    return None


def generate_insights(
    history: pd.DataFrame | None = None,
    forecast: pd.DataFrame | None = None,
    scenario_results: Any = None,
    sensitivity: pd.DataFrame | None = None,
    monte_carlo: dict[str, Any] | None = None,
    max_insights: int = 4,
) -> list[str]:
    """Generate concise observations whose values come directly from model output."""

    if max_insights <= 0:
        return []
    if forecast is None and history is not None:
        forecast = build_monthly_forecast(history)
    if sensitivity is None and history is not None:
        sensitivity = run_sensitivity(history)

    insights: list[str] = []
    if sensitivity is not None and not sensitivity.empty:
        ranked = sensitivity.sort_values("economic_materiality_eur")
        largest_driver = ranked.iloc[-1]["driver"]
        driver_rows = sensitivity.loc[sensitivity["driver"].eq(largest_driver)]
        favorable = driver_rows.loc[driver_rows["minimum_cash_impact_eur"].idxmax()]
        impact = float(favorable["minimum_cash_impact_eur"])
        if largest_driver == "DSO":
            insights.append(
                f"Collections are the largest modeled liquidity lever. The {favorable['shock']} DSO case changes minimum cash by {_money(impact)}."
            )
        else:
            insights.append(
                f"{largest_driver} is the most material tested driver; the {favorable['shock']} case changes minimum cash by {_money(impact)}."
            )

    scenarios = _scenario_frame(scenario_results)
    if scenarios is not None and {"scenario", "ebitda_eur", "minimum_cash_eur"}.issubset(scenarios.columns):
        base_rows = scenarios.loc[scenarios["scenario"].eq("Base")]
        hiring_rows = scenarios.loc[
            scenarios["scenario"].isin(["Hiring Expansion", "2026 Expansion Decision"])
        ]
        if not base_rows.empty and not hiring_rows.empty:
            base = base_rows.iloc[0]
            hiring = hiring_rows.iloc[0]
            ebitda_delta = float(hiring["ebitda_eur"] - base["ebitda_eur"])
            cash_delta = float(hiring["minimum_cash_eur"] - base["minimum_cash_eur"])
            if ebitda_delta > 0 and cash_delta < 0:
                insights.append(
                    f"The hiring plan is EBITDA-accretive by {_money(ebitda_delta)} but lowers minimum cash by {_money(abs(cash_delta))} during the ramp."
                )
            elif ebitda_delta <= 0:
                insights.append(
                    f"The tested hiring plan reduces forecast EBITDA by {_money(abs(ebitda_delta))}; ramp speed or demand needs strengthening before expansion."
                )

    if forecast is not None and not forecast.empty:
        threshold = (
            float(forecast["minimum_cash_threshold_eur"].iloc[-1])
            if "minimum_cash_threshold_eur" in forecast
            else 3_000_000.0
        )
        minimum_cash = float(forecast["closing_cash_eur"].min())
        minimum_month = pd.Timestamp(
            forecast.loc[forecast["closing_cash_eur"].idxmin(), "month"]
        ).strftime("%b %Y")
        if minimum_cash < threshold:
            insights.append(
                f"Cash falls below the {_money(threshold)} policy threshold in the forecast, reaching {_money(minimum_cash)} in {minimum_month}; modeled headroom is {_money(minimum_cash - threshold)}."
            )
        else:
            insights.append(
                f"Liquidity remains above the {_money(threshold)} policy threshold; the lowest modeled cash is {_money(minimum_cash)} in {minimum_month}."
            )

        first_revenue = float(forecast["revenue_eur"].head(3).mean())
        last_revenue = float(forecast["revenue_eur"].tail(3).mean())
        cash_change = float(
            forecast["closing_cash_eur"].iloc[-1] - forecast["opening_cash_eur"].iloc[0]
        )
        if last_revenue > first_revenue * 1.03 and cash_change < 0:
            insights.append(
                f"Revenue rises {last_revenue / first_revenue - 1:.1%} while cash declines {_money(abs(cash_change))}, indicating investment or working-capital pressure rather than a sales shortfall."
            )

    if monte_carlo and isinstance(monte_carlo.get("summary"), dict):
        summary = monte_carlo["summary"]
        breach_probability = float(summary.get("probability_cash_below_threshold", 0.0))
        p5 = float(summary.get("p5_year_end_cash_eur", 0.0))
        insights.append(
            f"Simulation risk is {breach_probability:.1%} for a minimum-cash breach; the 5th-percentile ending cash outcome is {_money(p5)}."
        )

    # Preserve order, remove exact duplicates, and respect the executive-page limit.
    return list(dict.fromkeys(insights))[:max_insights]


insights_from_results = generate_insights
