"""A small, visible Monte Carlo experiment for the student project."""

from __future__ import annotations

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from components.cards import callout, metric_card
from components.charts import COLORS, style_figure
from components.controls import dropdown, field
from components.data_access import load_dataset
from components.formatting import euro, percent
from models.monte_carlo import run_monte_carlo


dash.register_page(
    __name__,
    path="/monte-carlo",
    name="Risk Simulation",
    title="NovaPlan | Risk Simulation",
)


PLAN_OVERRIDES = {
    "base": None,
    "hire_40": {
        "incremental_hires_total": 40,
        "hire_joining_months": 6,
        "hire_ramp_months": 3,
    },
}


def layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="mc-summary-store"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Probability experiment", className="page-kicker"),
                            html.H1("What if the future is a little better or worse than planned?"),
                            html.P(
                                "Run the forecast many times while utilization, customer payments, prices and costs move by small random amounts."
                            ),
                        ]
                    )
                ],
                className="page-heading",
            ),
            callout(
                "Try this first",
                "Move uncertainty from 0% to 200%. The middle result should stay fairly stable, while the light P5–P95 band becomes much wider.",
                "info",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Experiment settings", className="controls-title"),
                            dropdown(
                                "mc-plan",
                                "Plan to test",
                                [
                                    {"label": "Current base plan", "value": "base"},
                                    {"label": "Hire 40 extra people", "value": "hire_40"},
                                ],
                                "base",
                                hint="The hiring plan changes the forecast before uncertainty is added.",
                            ),
                            field(
                                "Uncertainty level",
                                dcc.Slider(
                                    id="mc-uncertainty",
                                    min=0,
                                    max=200,
                                    step=25,
                                    value=100,
                                    marks={0: "0%", 50: "low", 100: "normal", 150: "high", 200: "extreme"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                    updatemode="mouseup",
                                ),
                                "0% removes random changes. A larger value widens every sampled business-driver range.",
                            ),
                            field(
                                "Cash safety target",
                                dcc.Slider(
                                    id="mc-threshold",
                                    min=14_000_000,
                                    max=18_000_000,
                                    step=500_000,
                                    value=16_000_000,
                                    marks={14_000_000: "€14m", 16_000_000: "€16m", 18_000_000: "€18m"},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                    updatemode="mouseup",
                                ),
                                "This line classifies results. It does not change the simulated cash paths.",
                            ),
                            field(
                                "Number of runs",
                                dcc.RadioItems(
                                    id="mc-simulations",
                                    options=[
                                        {"label": "2,000", "value": 2_000},
                                        {"label": "5,000", "value": 5_000},
                                        {"label": "10,000", "value": 10_000},
                                    ],
                                    value=5_000,
                                    inline=True,
                                    className="segmented-control",
                                ),
                                "More runs make the percentages steadier; they do not make the business risk larger.",
                            ),
                            html.Div(
                                [html.Strong("Fixed for repeatability: "), html.Span("random seed 42")],
                                className="model-note",
                            ),
                        ],
                        className="controls-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id="mc-kpis", className="metric-grid five"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H3("Range of possible cash outcomes"),
                                            html.P("The line is the middle result. The shaded area contains P5 to P95."),
                                        ],
                                        className="panel-header",
                                    ),
                                    dcc.Loading(
                                        dcc.Graph(id="mc-fan-chart", config={"displayModeBar": False}),
                                        type="circle",
                                    ),
                                ],
                                className="panel",
                            ),
                            html.Div(id="mc-conclusion"),
                        ]
                    ),
                ],
                className="content-grid sidebar-layout",
            ),
            html.Details(
                [
                    html.Summary("What should each control change?"),
                    html.Ul(
                        [
                            html.Li("Plan: moves the underlying forecast."),
                            html.Li("Uncertainty: changes the width of the outcome range."),
                            html.Li("Cash target: changes the breach percentage, not the paths."),
                            html.Li("Run count: makes the estimate smoother, not riskier."),
                        ]
                    ),
                ],
                className="panel soft",
            ),
        ]
    )


@callback(
    Output("mc-fan-chart", "figure"),
    Output("mc-kpis", "children"),
    Output("mc-conclusion", "children"),
    Output("mc-summary-store", "data"),
    Input("mc-plan", "value"),
    Input("mc-uncertainty", "value"),
    Input("mc-threshold", "value"),
    Input("mc-simulations", "value"),
)
def update_monte_carlo(
    plan: str | None,
    uncertainty: float | None,
    threshold: float | None,
    simulations: int | None,
):
    plan = plan if plan in PLAN_OVERRIDES else "base"
    uncertainty = 100.0 if uncertainty is None else float(uncertainty)
    threshold = 16_000_000.0 if threshold is None else float(threshold)
    simulations = 5_000 if simulations is None else int(simulations)

    history = load_dataset("monthly_kpis")
    result = run_monte_carlo(
        history,
        n_simulations=simulations,
        seed=42,
        threshold=threshold,
        assumptions={
            "uncertainty_scale": uncertainty / 100,
            "forecast_overrides": PLAN_OVERRIDES[plan],
        },
    )
    summary = result["summary"]
    fan = pd.DataFrame(result["fan_chart"])

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=fan["month"],
            y=fan["p95_cash_eur"],
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=fan["month"],
            y=fan["p5_cash_eur"],
            fill="tonexty",
            fillcolor="rgba(22,112,111,.15)",
            line=dict(width=0),
            name="P5–P95 range",
            hovertemplate="P5 €%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=fan["month"],
            y=fan["p50_cash_eur"],
            name="Middle result (P50)",
            line=dict(color=COLORS["accent"], width=3),
            hovertemplate="Middle €%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_hline(
        y=threshold,
        line_dash="dash",
        line_color=COLORS["amber"],
        annotation_text=f"Safety target {euro(threshold)}",
        annotation_position="bottom right",
    )
    figure.update_yaxes(tickprefix="€", tickformat=".3s")
    style_figure(figure, height=430)

    probability = float(summary["probability_cash_below_threshold"])
    p5 = float(summary["p5_year_end_cash_eur"])
    median = float(summary["median_year_end_cash_eur"])
    p95 = float(summary["p95_year_end_cash_eur"])
    spread = p95 - p5
    kpis = [
        metric_card("Chance below target", percent(probability), f"target {euro(threshold)}", tone="warning" if probability > 0.20 else "positive"),
        metric_card("Low result (P5)", euro(p5), "5% of end results are lower"),
        metric_card("Middle result", euro(median), "half lower, half higher"),
        metric_card("High result (P95)", euro(p95), "5% of end results are higher"),
        metric_card("Range width", euro(spread), "P95 minus P5"),
    ]

    if uncertainty == 0:
        message = "Uncertainty is off, so all runs follow the same path and the P5–P95 range collapses to zero."
    elif probability == 0:
        message = (
            "No run fell below the selected target. That means zero events were observed under these assumptions—not that real-world risk is zero."
        )
    else:
        message = (
            f"About {percent(probability)} of the {simulations:,} simulated paths fall below {euro(threshold)} at least once. "
            f"The end-of-horizon P5–P95 range is {euro(spread)} wide."
        )

    raw = {
        "plan": plan,
        "uncertainty_percent": uncertainty,
        "cash_safety_target_eur": threshold,
        "simulations": simulations,
        "seed": 42,
        "range_width_eur": spread,
        **summary,
    }
    return figure, kpis, callout("What the simulation says", message, "info"), raw
