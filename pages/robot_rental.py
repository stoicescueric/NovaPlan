"""Robot rental experiment: the lowest safe uptime, and profit versus cash."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from components.cards import callout, metric_card
from components.charts import COLORS, style_figure
from components.controls import field
from components.formatting import euro, number, percent
from models.robot_rental import (
    COMPANY_NAME,
    DEFAULT_RENTAL_ASSUMPTIONS,
    build_rental_forecast,
    find_uptime_threshold,
    run_rental_monte_carlo,
    uptime_sweep,
)
from models.working_capital import AVERAGE_DAYS_PER_MONTH


dash.register_page(
    __name__,
    path="/robot-rental",
    name="Robot Rental Experiment",
    title="NovaPlan | Robot Rental",
)


DEFAULTS = DEFAULT_RENTAL_ASSUMPTIONS
SIMULATIONS = 5_000
SWEEP_SIMULATIONS = 2_000
SEED = 42
THRESHOLD_SEARCH_FLOOR = 0.50
# Wider than the 80–100% uptime slider so the chart still shows where the risk
# starts when the lowest safe uptime is below 80%.
SWEEP_UPTIMES = tuple(float(value) for value in np.round(np.arange(0.60, 1.0001, 0.01), 2))


def _slider(component_id: str, label: str, minimum: float, maximum: float, step: float, value: float, marks: dict, hint: str):
    return field(
        label,
        dcc.Slider(
            id=component_id,
            min=minimum,
            max=maximum,
            step=step,
            value=value,
            marks=marks,
            tooltip={"placement": "bottom", "always_visible": True},
            updatemode="mouseup",
        ),
        hint,
    )


def _fixed_assumptions() -> html.Details:
    booked = float(DEFAULTS["booked_hours_per_robot_month"])
    rows = [
        f"Booked hours: {number(booked)} per placed robot per month",
        f"Robots placed with customers: {number(DEFAULTS['deploy_per_month'])} per month until the fleet is out",
        f"Repairs: {euro(DEFAULTS['repair_cost_per_down_hour_eur'])} per hour a robot is down",
        f"Service: {euro(DEFAULTS['service_cost_per_robot_month_eur'])} per placed robot per month",
        f"Staff, office and insurance: {euro(DEFAULTS['fixed_opex_month_eur'])} per month",
        f"Depreciation: straight line over {number(DEFAULTS['useful_life_months'])} months",
        f"Cash floor: {euro(DEFAULTS['cash_floor_eur'])} in every month",
        f"{SIMULATIONS:,} runs for the cash range and {SWEEP_SIMULATIONS:,} runs for each point on the uptime chart. "
        f"Random seed {SEED} is a bookmark: the same settings recreate the same result.",
    ]
    return html.Details(
        [html.Summary("Fixed assumptions")] + [html.P(row, className="model-note") for row in rows],
        className="advanced-settings",
    )


def layout() -> html.Div:
    booked = float(DEFAULTS["booked_hours_per_robot_month"])
    default_uptime = float(DEFAULTS["uptime"])
    return html.Div(
        [
            dcc.Store(id="robot-rental-results"),
            html.Div(
                [
                    html.Div(
                        [
                            html.H1(
                                "What is the lowest uptime at which a robot-rental company keeps enough cash to survive, and can it run out of cash while still reporting a profit?"
                            ),
                            html.P(
                                f"{COMPANY_NAME} buys robots and rents them to factories by the hour. Customers pay weeks later, and a robot that is down earns nothing."
                            ),
                        ]
                    )
                ],
                className="page-heading",
            ),
            html.P("Fictional company, illustrative numbers.", className="research-note"),
            html.P(
                [html.Strong("Try this: "), "Set the payment delay to 90 days and opening cash to €550k. Profit does not change, but some runs now dip below the cash floor while still reporting a profit."],
                className="experiment-note",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Experiment settings", className="controls-title"),
                            _slider(
                                "robot-fleet",
                                "Robots bought",
                                4,
                                16,
                                1,
                                DEFAULTS["fleet_size"],
                                {4: "4", 10: "10", 16: "16"},
                                f"Every robot is paid for in month 0, and {number(DEFAULTS['deploy_per_month'])} are placed with customers each month until the whole fleet is out. More robots mean more rent later but less cash left after buying them. This does not change the price, uptime or payment time.",
                            ),
                            _slider(
                                "robot-cost",
                                "Price per robot",
                                30_000,
                                60_000,
                                2_500,
                                DEFAULTS["robot_cost_eur"],
                                {30_000: "€30k", 45_000: "€45k", 60_000: "€60k"},
                                f"What one robot costs, including setting it up on the customer’s line. The cash leaves in month 0, but profit only feels it slowly, through depreciation over {number(DEFAULTS['useful_life_months'])} months. Rent and running costs do not change.",
                            ),
                            _slider(
                                "robot-rate",
                                "Rental price per working hour",
                                15,
                                30,
                                1,
                                DEFAULTS["hourly_rate_eur"],
                                {15: "€15", 22: "€22", 30: "€30"},
                                "Customers pay this for every hour a robot actually works; a down hour earns nothing at any price. A higher price raises revenue, profit and cash, but not the number of hours.",
                            ),
                            _slider(
                                "robot-uptime",
                                "Uptime",
                                80,
                                100,
                                1,
                                round(default_uptime * 100),
                                {80: "80%", 85: "85%", 90: "90%", 95: "95%", 100: "100%"},
                                f"The share of booked hours a robot really works. At {percent(default_uptime, 0)}, a robot booked for {number(booked)} hours works {number(booked * default_uptime)} and is down for {number(booked * (1 - default_uptime))}. Each down hour earns no rent and costs {euro(DEFAULTS['repair_cost_per_down_hour_eur'])} of repairs.",
                            ),
                            _slider(
                                "robot-dso",
                                "Days customers take to pay",
                                0,
                                120,
                                15,
                                DEFAULTS["dso_days"],
                                {0: "0", 45: "45", 90: "90", 120: "120"},
                                "Rent counts as profit in the month the robot works, but the money arrives this many days later. A longer wait lowers cash; it does not change revenue or profit.",
                            ),
                            _slider(
                                "robot-cash",
                                "Opening cash",
                                450_000,
                                900_000,
                                25_000,
                                DEFAULTS["opening_cash_eur"],
                                {450_000: "€450k", 600_000: "€600k", 750_000: "€750k", 900_000: "€900k"},
                                "Money in the bank before the robots are bought. It has to cover the purchase, the slow start and the wait for customer payments. It does not change profit.",
                            ),
                            field(
                                "Uncertainty level",
                                dcc.Slider(
                                    id="robot-uncertainty",
                                    min=0,
                                    max=200,
                                    step=25,
                                    value=100,
                                    marks={0: "0%", 50: "50%", 100: "100%", 150: "150%", 200: "200%"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                    updatemode="mouseup",
                                ),
                                f"0% removes the wobble, so every run follows the plan. At 100%, each run’s average uptime moves by about {DEFAULTS['uptime_path_std_pp'] * 100:g} percentage points (plus {DEFAULTS['uptime_monthly_std_pp'] * 100:g} point month to month), its payment time by about {DEFAULTS['dso_path_std_days']:g} days and its booked hours by about {DEFAULTS['booked_hours_path_std_pct'] * 100:g}%. 200% doubles those ranges. The settings above stay fixed.",
                            ),
                            _fixed_assumptions(),
                        ],
                        className="controls-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id="robot-kpis", className="metric-grid"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H3("Cash range and profit over 36 months"),
                                            html.P("The shaded band holds the middle 90% of runs (P5 to P95). The amber line is profit so far in the plan without randomness, on the same € scale."),
                                        ],
                                        className="panel-header",
                                    ),
                                    dcc.Loading(
                                        dcc.Graph(id="robot-fan-chart", config={"displayModeBar": False}),
                                        type="circle",
                                    ),
                                ],
                                className="panel",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H3("Chance of running short at each uptime"),
                                            html.P(f"Each point repeats {SWEEP_SIMULATIONS:,} runs at that average uptime. The amber line shows how many of the short-of-cash runs were still profitable; it is empty where no run went short."),
                                        ],
                                        className="panel-header",
                                    ),
                                    dcc.Loading(
                                        dcc.Graph(id="robot-sweep-chart", config={"displayModeBar": False}),
                                        type="circle",
                                    ),
                                ],
                                className="panel",
                            ),
                            html.Div(id="robot-explanation"),
                        ],
                        className="results-stack",
                    ),
                ],
                className="content-grid sidebar-layout",
            ),
        ],
        className="primary-page",
    )


def _assumptions(business: tuple[float, ...], uptime: float | None = None) -> dict[str, float]:
    fleet_size, robot_cost, hourly_rate, dso_days, opening_cash = business
    values = {
        "fleet_size": fleet_size,
        "robot_cost_eur": robot_cost,
        "hourly_rate_eur": hourly_rate,
        "dso_days": dso_days,
        "opening_cash_eur": opening_cash,
    }
    if uptime is not None:
        values["uptime"] = uptime
    return values


@lru_cache(maxsize=64)
def _threshold(business: tuple[float, ...]) -> float | None:
    return find_uptime_threshold(_assumptions(business), lower=THRESHOLD_SEARCH_FLOOR)


@lru_cache(maxsize=64)
def _simulation(business: tuple[float, ...], uptime: float, scale: float) -> dict[str, Any]:
    # Keep only what the page shows, so cached entries stay small.
    result = run_rental_monte_carlo(
        _assumptions(business, uptime),
        n_simulations=SIMULATIONS,
        seed=SEED,
        uncertainty_scale=scale,
    )
    keys = ("percentiles", "breach_probability", "profitable_but_broke_share", "breach_count", "profitable_but_broke_count")
    return {key: result[key] for key in keys}


@lru_cache(maxsize=32)
def _sweep(business: tuple[float, ...], scale: float) -> pd.DataFrame:
    # Uptime is not part of the key: the sweep varies uptime itself.
    return uptime_sweep(
        _assumptions(business),
        uptimes=SWEEP_UPTIMES,
        n_simulations=SWEEP_SIMULATIONS,
        seed=SEED,
        uncertainty_scale=scale,
    )


def _fan_figure(percentiles: pd.DataFrame, forecast: pd.DataFrame, floor: float) -> go.Figure:
    months = percentiles["month"]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=months,
            y=percentiles["p95_cash_eur"],
            line=dict(width=0),
            showlegend=False,
            hovertemplate="P95 cash €%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=months,
            y=percentiles["p5_cash_eur"],
            fill="tonexty",
            fillcolor="rgba(31,98,85,.14)",
            line=dict(width=0),
            name="Cash, P5–P95 range",
            hovertemplate="P5 cash €%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=months,
            y=percentiles["p50_cash_eur"],
            name="Cash, middle run (P50)",
            line=dict(color=COLORS["accent"], width=3),
            hovertemplate="Middle cash €%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast["month"],
            y=forecast["cumulative_profit_eur"],
            name="Profit so far (plan)",
            yaxis="y2",
            line=dict(color=COLORS["amber"], width=2),
            hovertemplate="Profit so far €%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_hline(
        y=floor,
        line_dash="dash",
        line_color=COLORS["red"],
        annotation_text=f"Cash floor {euro(floor)}",
        annotation_position="bottom right",
    )
    # A second axis as a reading aid only: it is locked to the cash axis, so the
    # gap between the profit line and the cash band is a real euro amount.
    figure.update_layout(yaxis2=dict(overlaying="y", side="right", matches="y", showgrid=False))
    style_figure(figure, height=400)
    figure.update_xaxes(title_text="Month (0 = robots bought)", dtick=6)
    figure.update_yaxes(tickprefix="€", tickformat=".3s")
    return figure


def _sweep_figure(sweep: pd.DataFrame, uptime: float, threshold: float | None) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=sweep["uptime"],
            y=sweep["breach_probability"],
            name="Chance of running short of cash",
            line=dict(color=COLORS["accent"], width=3),
            hovertemplate="Short of cash %{y:.1%}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=sweep["uptime"],
            y=sweep["profitable_but_broke_share"],
            name="Of those runs, still profitable",
            line=dict(color=COLORS["amber"], width=2),
            hovertemplate="Still profitable %{y:.1%}<extra></extra>",
        )
    )
    # Reference lines are named in the legend rather than labelled on the plot,
    # where a label would collide with the curves at some settings.
    figure.add_trace(
        go.Scatter(
            x=[uptime, uptime],
            y=[0, 1],
            mode="lines",
            name=f"Your uptime ({percent(uptime, 0)})",
            line=dict(color=COLORS["ink"], width=1),
            hoverinfo="skip",
        )
    )
    if threshold is not None and SWEEP_UPTIMES[0] <= threshold <= SWEEP_UPTIMES[-1]:
        figure.add_trace(
            go.Scatter(
                x=[threshold, threshold],
                y=[0, 1],
                mode="lines",
                name=f"Lowest safe uptime ({percent(threshold)})",
                line=dict(color=COLORS["red"], width=1.5, dash="dash"),
                hoverinfo="skip",
            )
        )
    style_figure(figure, height=340)
    figure.update_xaxes(
        title_text="Average uptime",
        tickformat=".0%",
        hoverformat=".0%",
        range=[SWEEP_UPTIMES[0] - 0.005, SWEEP_UPTIMES[-1] + 0.005],
    )
    figure.update_yaxes(tickformat=".0%", range=[-0.03, 1.05])
    return figure


@callback(
    Output("robot-fan-chart", "figure"),
    Output("robot-sweep-chart", "figure"),
    Output("robot-kpis", "children"),
    Output("robot-explanation", "children"),
    Output("robot-rental-results", "data"),
    Input("robot-fleet", "value"),
    Input("robot-cost", "value"),
    Input("robot-rate", "value"),
    Input("robot-uptime", "value"),
    Input("robot-dso", "value"),
    Input("robot-cash", "value"),
    Input("robot-uncertainty", "value"),
)
def update_robot_rental(
    fleet_size: float | None,
    robot_cost: float | None,
    hourly_rate: float | None,
    uptime: float | None,
    dso_days: float | None,
    opening_cash: float | None,
    uncertainty: float | None,
):
    business = (
        float(DEFAULTS["fleet_size"] if fleet_size is None else fleet_size),
        float(DEFAULTS["robot_cost_eur"] if robot_cost is None else robot_cost),
        float(DEFAULTS["hourly_rate_eur"] if hourly_rate is None else hourly_rate),
        float(DEFAULTS["dso_days"] if dso_days is None else dso_days),
        float(DEFAULTS["opening_cash_eur"] if opening_cash is None else opening_cash),
    )
    uptime = float(DEFAULTS["uptime"]) if uptime is None else float(uptime) / 100
    uncertainty = 100.0 if uncertainty is None else float(uncertainty)
    scale = uncertainty / 100

    forecast = build_rental_forecast(_assumptions(business, uptime))
    threshold = _threshold(business)
    simulation = _simulation(business, uptime, scale)
    sweep = _sweep(business, scale)
    floor = float(DEFAULTS["cash_floor_eur"])
    months = int(DEFAULTS["months"])

    breach_probability = float(simulation["breach_probability"])
    breach_count = int(simulation["breach_count"])
    profitable_count = int(simulation["profitable_but_broke_count"])
    profitable_share = float(simulation["profitable_but_broke_share"])

    if threshold is None:
        threshold_card = metric_card(
            "Lowest safe uptime",
            "None",
            "even 100% uptime runs short",
            tone="negative",
            explanation=f"Even at 100% uptime, the plan without randomness drops below the {euro(floor)} cash floor in at least one month. More opening cash, fewer or cheaper robots, a higher price or faster-paying customers are needed.",
        )
    else:
        at_search_floor = threshold <= THRESHOLD_SEARCH_FLOOR
        threshold_card = metric_card(
            "Lowest safe uptime",
            f"≤ {percent(threshold, 0)}" if at_search_floor else percent(threshold),
            f"your plan: {percent(uptime, 0)}",
            tone="positive" if uptime >= threshold else "negative",
            explanation=f"The lowest uptime at which the plan without randomness keeps cash at or above the {euro(floor)} floor in every one of the {months} months. It is found by halving the search range between {percent(THRESHOLD_SEARCH_FLOOR, 0)} and 100% until it is narrower than 0.01 percentage points. The uncertainty level does not change it.",
        )
    kpis = [
        threshold_card,
        metric_card(
            "Chance of running short of cash",
            percent(breach_probability),
            f"{breach_count:,} of {SIMULATIONS:,} runs",
            tone="positive" if breach_count == 0 else "negative" if breach_probability > 0.05 else "warning",
            explanation=f"The share of simulated runs whose cash drops below the {euro(floor)} floor in at least one month. Zero means no run went below the floor under these assumptions—not that real-world risk is zero.",
        ),
        metric_card(
            "Short of cash while still profitable",
            "—" if breach_count == 0 else percent(profitable_share),
            "no run went short" if breach_count == 0 else f"{profitable_count:,} of {breach_count:,} short runs",
            tone="neutral" if profitable_count == 0 else "warning",
            explanation="Among the runs that go below the cash floor, the share whose operating profit added up since month 0 is still positive in the month cash first drops below the floor. On paper these companies make money; in the bank they cannot keep the floor.",
        ),
    ]

    rate = business[2]
    repair = float(DEFAULTS["repair_cost_per_down_hour_eur"])
    dso = business[3]
    if threshold is None:
        threshold_sentence = f"With these settings no uptime is safe: even at 100% the plan without randomness drops below the {euro(floor)} cash floor."
    elif threshold <= THRESHOLD_SEARCH_FLOOR:
        threshold_sentence = f"With these settings every uptime from {percent(THRESHOLD_SEARCH_FLOOR, 0)} up keeps the plan without randomness above the {euro(floor)} cash floor, so uptime is not the limit."
    else:
        threshold_sentence = f"The lowest safe uptime, {percent(threshold)}, is where the plan without randomness just stays above the {euro(floor)} cash floor in all {months} months: below it the plan itself runs short, and above it only unlucky runs do."
    explanation = callout(
        "Why cash and profit move differently",
        f"Downtime hits cash twice: a robot that is down earns no rent ({euro(rate)} an hour) and still needs repairs ({euro(repair)} an hour), so each lost hour costs about {euro(rate + repair)}. "
        f"Payment delay is different: rent counts as profit in the month the robot works, but at {dso:.0f} days the money arrives about {dso / AVERAGE_DAYS_PER_MONTH:.1f} months later, so a longer delay lowers cash but not profit. "
        f"{threshold_sentence}",
        "info",
    )

    percentiles = simulation["percentiles"]
    raw = {
        "fleet_size": business[0],
        "robot_cost_eur": business[1],
        "hourly_rate_eur": business[2],
        "uptime": uptime,
        "dso_days": business[3],
        "opening_cash_eur": business[4],
        "uncertainty_percent": uncertainty,
        "simulations": SIMULATIONS,
        "seed": SEED,
        "lowest_safe_uptime": threshold,
        "breach_probability": breach_probability,
        "breach_count": breach_count,
        "profitable_but_broke_share": None if breach_count == 0 else profitable_share,
        "profitable_but_broke_count": profitable_count,
        "minimum_cash_eur": float(forecast["closing_cash_eur"].min()),
        "ending_cash_eur": float(forecast["closing_cash_eur"].iloc[-1]),
        "total_revenue_eur": float(forecast["revenue_eur"].sum()),
        "total_operating_profit_eur": float(forecast["operating_profit_eur"].sum()),
        "range_width_eur": float(percentiles["p95_cash_eur"].iloc[-1] - percentiles["p5_cash_eur"].iloc[-1]),
    }
    return (
        _fan_figure(percentiles, forecast, floor),
        _sweep_figure(sweep, uptime, threshold),
        kpis,
        explanation,
        raw,
    )
