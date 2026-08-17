"""Simple landing page for the student internship project."""

from __future__ import annotations

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from components.cards import metric_card
from components.charts import COLORS, style_figure
from components.data_access import load_dataset
from components.formatting import euro, percent
from models.scenarios import run_scenario


dash.register_page(__name__, path="/", name="Project Overview", title="NovaPlan | Student Project")


def _history_chart(history: pd.DataFrame) -> go.Figure:
    history = history.copy()
    history["month"] = pd.to_datetime(history["month"])
    annual = history.groupby(history["month"].dt.year).agg(
        revenue_eur=("revenue_eur", "sum"),
        closing_cash_eur=("closing_cash_eur", "last"),
    )
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=annual.index,
            y=annual["revenue_eur"],
            name="Revenue",
            marker_color=COLORS["blue"],
            hovertemplate="%{x}<br>Revenue €%{y:,.0f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=annual.index,
            y=annual["closing_cash_eur"],
            name="Cash at year end",
            mode="lines+markers",
            line=dict(color=COLORS["accent"], width=3),
            hovertemplate="%{x}<br>Cash €%{y:,.0f}<extra></extra>",
        )
    )
    figure.update_yaxes(tickprefix="€", tickformat=".3s")
    return style_figure(figure, height=330)


def layout() -> html.Div:
    history = load_dataset("monthly_kpis")
    latest_year = history.tail(12)
    base = run_scenario(history, "Base")
    # Match the default What-if page exactly: 40 hires, with no hidden
    # collection or demand assumption added to the example.
    expansion = run_scenario(
        history,
        "Custom",
        {
            "incremental_hires_total": 40,
            "hire_joining_months": 6,
            "hire_ramp_months": 3,
        },
    )

    revenue = float(latest_year["revenue_eur"].sum())
    ebitda = float(latest_year["ebitda_eur"].sum())
    margin = ebitda / revenue if revenue else 0.0
    starting_cash = float(history.iloc[-1]["closing_cash_eur"])
    base_minimum = float(base["summary"]["minimum_cash_eur"])
    expansion_minimum = float(expansion["summary"]["minimum_cash_eur"])
    expansion_minimum_change = expansion_minimum - base_minimum
    expansion_profit_change = float(
        expansion["summary"]["ebitda_eur"] - base["summary"]["ebitda_eur"]
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H1("Can a consulting company hire more people without running short of cash?"),
                            html.P(
                                "We built this project with a fictional company to study one chain of cause and effect: people create capacity, capacity creates revenue, costs shape profit, and payment timing turns that profit into cash."
                            ),
                        ]
                    ),
                    dcc.Link("Try the what-if experiment", href="/what-if", className="button"),
                ],
                className="page-heading",
            ),
            html.Div(
                [
                    metric_card(
                        "Synthetic history",
                        "72 months",
                        "2020–2025",
                        explanation="Six years of invented but internally connected monthly records.",
                    ),
                    metric_card(
                        "2025 revenue",
                        euro(revenue),
                        "services earned",
                        explanation="The value of consulting services delivered during 2025.",
                    ),
                    metric_card(
                        "Operating profit margin",
                        percent(margin),
                        "EBITDA ÷ revenue",
                        explanation="The share of revenue left after the main operating costs.",
                    ),
                    metric_card(
                        "Lowest planned cash",
                        euro(base_minimum),
                        f"starts at {euro(starting_cash)}",
                        explanation="The lowest monthly cash balance in the 18-month base plan.",
                    ),
                ],
                className="metric-grid four",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3("What happened from 2020 to 2025?"),
                                    html.P("Revenue grew, but cash followed a different path because invoices are paid later."),
                                ],
                                className="panel-header",
                            ),
                            dcc.Graph(figure=_history_chart(history), config={"displayModeBar": False}),
                            html.P(
                                "Bars show annual revenue. The line shows cash at each year end. They are related, but they are not the same thing.",
                                className="chart-guide",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H3("Practical result", style={"marginTop": "22px"}),
                            html.P(
                                f"The 40-person hiring example adds about {euro(expansion_profit_change)} of forecast EBITDA, while the lowest cash point is {euro(abs(expansion_minimum_change))} lower during ramp-up."
                            ),
                            dcc.Link("Change the four main assumptions →", href="/what-if", className="button secondary"),
                        ],
                        className="panel soft",
                    ),
                ],
                className="content-grid equal",
            ),
        ],
        className="primary-page",
    )
