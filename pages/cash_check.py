"""Small 13-week cash experiment for the student project."""

from __future__ import annotations

import numpy as np
import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from components.cards import callout, metric_card
from components.charts import COLORS, style_figure
from components.controls import field
from components.data_access import load_dataset
from components.formatting import euro
from models.cashflow import build_13_week_forecast


dash.register_page(__name__, path="/cash-check", name="13-Week Cash Check", title="NovaPlan | Cash Check")


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


def layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="cash-check-results"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Short-term cash experiment", className="page-kicker"),
                            html.H1("Will we have enough cash for the next 13 weeks?"),
                            html.P("Test three simple events and look for the lowest weekly balance."),
                        ]
                    )
                ],
                className="page-heading",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Try a short-term change", className="controls-title"),
                            _slider(
                                "cash-delay",
                                "Customer payment delay",
                                0,
                                28,
                                7,
                                0,
                                {0: "none", 14: "2 weeks", 28: "4 weeks"},
                                "Later customer payments move cash receipts into later weeks.",
                            ),
                            _slider(
                                "cash-hires",
                                "Extra employees joining now",
                                0,
                                40,
                                5,
                                0,
                                {0: "0", 20: "20", 40: "40"},
                                "New employees add payroll, recruiting and equipment costs.",
                            ),
                            _slider(
                                "cash-extra-cost",
                                "Unexpected payment in week 1",
                                0,
                                2_000_000,
                                250_000,
                                0,
                                {0: "€0", 1_000_000: "€1m", 2_000_000: "€2m"},
                                "This represents a one-time bill, tax payment or equipment purchase.",
                            ),
                        ],
                        className="controls-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id="cash-check-kpis", className="metric-grid four"),
                            html.Div(
                                [
                                    html.Div(
                                        [html.H3("Weekly closing cash"), html.P("The lowest dot is the tightest cash week.")],
                                        className="panel-header",
                                    ),
                                    dcc.Graph(id="cash-check-chart", config={"displayModeBar": False}),
                                ],
                                className="panel",
                            ),
                            html.Div(id="cash-check-conclusion"),
                        ]
                    ),
                ],
                className="content-grid sidebar-layout",
            ),
        ]
    )


@callback(
    Output("cash-check-chart", "figure"),
    Output("cash-check-kpis", "children"),
    Output("cash-check-conclusion", "children"),
    Output("cash-check-results", "data"),
    Input("cash-delay", "value"),
    Input("cash-hires", "value"),
    Input("cash-extra-cost", "value"),
)
def update_cash_check(delay: float | None, hires: float | None, extra_cost: float | None):
    delay = 0 if delay is None else int(delay)
    hires = 0 if hires is None else int(hires)
    extra_cost = 0.0 if extra_cost is None else float(extra_cost)

    history = load_dataset("monthly_kpis")
    invoices = load_dataset("invoices")
    other_payments = np.zeros(13)
    other_payments[0] = extra_cost
    forecast = build_13_week_forecast(
        history,
        invoices,
        {
            "collection_delay_days": delay,
            "incremental_hires": hires,
            "weekly_other_payments_eur": other_payments,
            "minimum_cash_threshold_eur": 3_000_000,
        },
    )

    cash = forecast["closing_cash_eur"]
    minimum_cash = float(cash.min())
    minimum_row = forecast.loc[cash.idxmin()]
    ending_cash = float(cash.iloc[-1])
    opening_cash = float(forecast["opening_cash_eur"].iloc[0])
    headroom = minimum_cash - 3_000_000

    figure = go.Figure(
        go.Scatter(
            x=forecast["week_start"],
            y=cash,
            name="Closing cash",
            mode="lines+markers",
            line=dict(color=COLORS["accent"], width=3),
            marker=dict(
                size=7,
                color=[COLORS["red"] if value < 3_000_000 else COLORS["accent"] for value in cash],
            ),
        )
    )
    figure.add_hline(
        y=3_000_000,
        line_dash="dash",
        line_color=COLORS["amber"],
        annotation_text="€3m minimum safe cash",
        annotation_position="bottom right",
    )
    figure.update_yaxes(tickprefix="€", tickformat=".3s")
    style_figure(figure, height=400)

    kpis = [
        metric_card("Opening cash", euro(opening_cash), "week 1"),
        metric_card("Lowest cash", euro(minimum_cash), f"week {int(minimum_row['week_number'])}", tone="positive" if minimum_cash >= 3_000_000 else "negative"),
        metric_card("Cash cushion", euro(headroom), "above the €3m level", tone="positive" if headroom >= 0 else "negative"),
        metric_card("Cash after 13 weeks", euro(ending_cash), "end of the short-term plan"),
    ]
    if headroom >= 0:
        message = f"The plan stays above €3m. Its smallest cash cushion is {euro(headroom)} in week {int(minimum_row['week_number'])}."
        tone = "info"
    else:
        message = f"The plan falls {euro(abs(headroom))} below the €3m safety level in week {int(minimum_row['week_number'])}."
        tone = "warning"

    raw = {
        "payment_delay_days": delay,
        "extra_hires": hires,
        "unexpected_payment_eur": extra_cost,
        "opening_cash_eur": opening_cash,
        "minimum_cash_eur": minimum_cash,
        "minimum_cash_week": int(minimum_row["week_number"]),
        "ending_cash_eur": ending_cash,
        "cash_headroom_eur": headroom,
    }
    return figure, kpis, callout("Cash check", message, tone), raw
