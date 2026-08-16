"""Direct 13-week liquidity forecast and short-term management levers."""

from __future__ import annotations

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html
from plotly.subplots import make_subplots

from components.cards import callout, metric_card, status_pill
from components.charts import COLORS, empty_figure, style_figure
from components.controls import number_input
from components.data_access import load_dataset
from components.formatting import euro
from components.learning import chart_guide, learning_guide, teaching_callout
from components.page_utils import first_column, first_date_column
from components.tables import data_table
from models.cashflow import build_13_week_forecast


dash.register_page(
    __name__,
    path="/liquidity",
    name="13-Week Liquidity",
    title="NovaPlan | 13-Week Liquidity",
)


def layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="liquidity-forecast-store"),
            dcc.Download(id="liquidity-download"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Direct cash forecast", className="page-kicker"),
                            html.H1("13-week liquidity control tower"),
                            html.P("Translate invoice timing and scheduled payments into a week-by-week view of cash headroom."),
                        ]
                    ),
                    html.Div(
                        [
                            status_pill("Invoice-level collections", "positive"),
                            html.Button("Export forecast", id="liquidity-export", className="button secondary"),
                        ],
                        className="page-heading-actions",
                    ),
                ],
                className="page-heading",
            ),
            learning_guide(
                "Use this page to check whether enough cash will be available for every payment over the next 13 weeks.",
                [
                    ("Set a realistic case", "Adjust collection timing, planned payments, hiring, and the cash safety threshold on the left."),
                    ("Find the lowest week", "Read the four headline metrics and check whether the cash line falls below the threshold."),
                    ("Understand the movement", "Use the receipts and disbursements chart and weekly schedule to see exactly what brings cash in and sends it out."),
                ],
                concepts=["Opening cash", "Collections", "Disbursements", "Closing cash", "Headroom", "Funding need"],
                open_by_default=True,
            ),
            teaching_callout(
                "A direct cash forecast follows actual money movements",
                "This forecast starts with cash already in the bank, adds expected customer receipts, and subtracts payments due each week. It focuses on payment dates, not when revenue or expenses are recorded in accounting.",
                formula="Closing cash = Opening cash + Collections − Disbursements",
                example="If a customer pays next week, the receipt appears next week even if the invoice was issued last month.",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Management levers", className="controls-title"),
                            html.P("Change the timing assumptions that can move cash before they affect profit.", className="controls-description"),
                            html.Div(
                                [
                                    number_input(
                                        "liq-collection-delay",
                                        "Collection delay",
                                        0,
                                        minimum=-20,
                                        maximum=45,
                                        step=1,
                                        suffix="days",
                                        hint="Positive days move customer receipts later and usually reduce near-term cash; negative days bring them forward.",
                                    ),
                                    number_input(
                                        "liq-large-payment",
                                        "Large customer payment",
                                        0,
                                        minimum=-2_000_000,
                                        maximum=2_000_000,
                                        step=50_000,
                                        suffix="EUR",
                                        hint="A positive amount adds an extra receipt in week 1; a negative amount reduces week 1 collections.",
                                    ),
                                    number_input(
                                        "liq-capex-shift",
                                        "Capex timing shift",
                                        0,
                                        minimum=-6,
                                        maximum=6,
                                        step=1,
                                        suffix="weeks",
                                        hint="Positive weeks postpone equipment or project payments; negative weeks bring those payments forward.",
                                    ),
                                    number_input(
                                        "liq-hires",
                                        "Incremental hires",
                                        0,
                                        minimum=0,
                                        maximum=60,
                                        step=5,
                                        suffix="FTE",
                                        hint="Adding full-time employees increases modeled payroll payments and usually lowers weekly cash.",
                                    ),
                                    number_input(
                                        "liq-discretionary",
                                        "Discretionary spend",
                                        0,
                                        minimum=-30,
                                        maximum=30,
                                        step=1,
                                        suffix="%",
                                        hint="A positive percentage increases adjustable supplier spending; a negative percentage models cost reductions.",
                                    ),
                                    number_input(
                                        "liq-threshold",
                                        "Minimum cash threshold",
                                        3_000_000,
                                        minimum=500_000,
                                        maximum=10_000_000,
                                        step=100_000,
                                        suffix="EUR",
                                        hint="Changes the safety floor used to measure headroom and funding need; it does not change forecast cash itself.",
                                    ),
                                ],
                                className="controls-grid one",
                            ),
                            html.Div(
                                "Revenue recognition is unchanged when customer payments move. The difference appears in AR and cash.",
                                className="model-note",
                                style={"marginTop": "16px"},
                            ),
                        ],
                        className="controls-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id="liquidity-kpis", className="metric-grid four"),
                            html.Div(
                                [
                                    html.Div(
                                        [html.H3("Weekly closing cash"), html.P("Where is the low point, and how much headroom remains?")],
                                        className="panel-header",
                                    ),
                                    chart_guide(
                                        "The line is the cash expected at the end of each week. The dashed line is your minimum cash threshold. Red points mark weeks below that floor; the lowest point is the week with the greatest liquidity pressure."
                                    ),
                                    dcc.Loading(
                                        dcc.Graph(id="liquidity-cash-chart", figure=empty_figure("Calculating forecast…"), config={"displayModeBar": False}),
                                        type="circle",
                                    ),
                                ],
                                className="panel",
                            ),
                        ]
                    ),
                ],
                className="content-grid sidebar-layout",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Receipts and disbursements"), html.P("What creates each weekly cash movement?")], className="panel-header"),
                            chart_guide(
                                "Bars above zero are customer collections coming in. Bars below zero are payroll, supplier, tax, and capex payments going out. The dark line uses the right-hand scale and shows the resulting closing cash balance."
                            ),
                            dcc.Graph(id="liquidity-bridge-chart", figure=empty_figure(), config={"displayModeBar": False}),
                        ],
                        className="panel",
                    ),
                    html.Div(id="liquidity-conclusion"),
                ],
                className="content-grid",
            ),
            html.Div(
                [
                    html.Div([html.H3("Weekly direct cash schedule"), html.P("Opening cash + collections − scheduled payments = closing cash")], className="panel-header"),
                    data_table(
                        "liquidity-table",
                        [],
                        columns=[
                            {"name": "Week", "id": "week"},
                            {"name": "Opening cash", "id": "opening_cash"},
                            {"name": "Collections", "id": "collections"},
                            {"name": "Payroll", "id": "payroll"},
                            {"name": "Suppliers", "id": "suppliers"},
                            {"name": "Tax", "id": "tax"},
                            {"name": "Capex", "id": "capex"},
                            {"name": "Closing cash", "id": "closing_cash"},
                        ],
                        page_size=13,
                    ),
                ],
                className="panel",
            ),
        ]
    )


@callback(
    Output("liquidity-cash-chart", "figure"),
    Output("liquidity-bridge-chart", "figure"),
    Output("liquidity-kpis", "children"),
    Output("liquidity-conclusion", "children"),
    Output("liquidity-table", "data"),
    Output("liquidity-forecast-store", "data"),
    Input("liq-collection-delay", "value"),
    Input("liq-large-payment", "value"),
    Input("liq-capex-shift", "value"),
    Input("liq-hires", "value"),
    Input("liq-discretionary", "value"),
    Input("liq-threshold", "value"),
)
def update_liquidity(
    collection_delay: float,
    large_payment: float,
    capex_shift: float,
    hires: float,
    discretionary_change: float,
    threshold: float,
):
    history = load_dataset("monthly_kpis")
    invoices = load_dataset("invoices")
    baseline = build_13_week_forecast(history, invoices)
    base_capex = first_column(baseline, ["capex_eur"]).to_numpy(float)
    shift = int(capex_shift or 0)
    shifted_capex = np.zeros_like(base_capex)
    for index, value in enumerate(base_capex):
        target_index = index + shift
        if 0 <= target_index < len(shifted_capex):
            shifted_capex[target_index] += value
        elif target_index < 0:
            shifted_capex[0] += value
        else:
            shifted_capex[-1] += value
    latest_headcount = max(float(history.iloc[-1].get("headcount", 1)), 1.0)
    assumptions = {
        "collection_delay_days": collection_delay or 0,
        "large_customer_payment_eur": large_payment or 0,
        "weekly_capex_eur": shifted_capex,
        "payroll_multiplier": 1 + (float(hires or 0) / latest_headcount) * 0.55,
        "vendor_payments_multiplier": 1 + (discretionary_change or 0) / 100 * 0.45,
        "minimum_cash_threshold_eur": threshold or 3_000_000,
    }
    forecast = build_13_week_forecast(history, invoices, assumptions)
    weeks = first_date_column(forecast, ["week_start", "week_end", "date"])
    closing = first_column(forecast, ["closing_cash_eur", "ending_cash_eur"])
    opening = first_column(forecast, ["opening_cash_eur"])
    collections = first_column(forecast, ["customer_collections_eur", "collections_eur"])
    payroll = first_column(forecast, ["payroll_eur"])
    suppliers = first_column(forecast, ["vendor_payments_eur", "supplier_payments_eur"])
    tax = first_column(forecast, ["tax_payments_eur", "tax_eur"])
    capex = first_column(forecast, ["capex_eur"])
    other = first_column(forecast, ["other_scheduled_payments_eur", "other_payments_eur"])
    threshold_value = threshold or 3_000_000

    cash_figure = go.Figure()
    cash_figure.add_trace(
        go.Scatter(
            x=weeks,
            y=closing,
            name="Closing cash",
            mode="lines+markers",
            line=dict(color=COLORS["accent"], width=3),
            marker=dict(size=6, color=[COLORS["red"] if value < threshold_value else COLORS["accent"] for value in closing]),
            fill="tozeroy",
            fillcolor="rgba(22,112,111,.06)",
            hovertemplate="%{x|%d %b}<br>€%{y:,.0f}<extra>Closing cash</extra>",
        )
    )
    cash_figure.add_hline(
        y=threshold_value,
        line_dash="dash",
        line_color=COLORS["amber"],
        annotation_text=f"Floor {euro(threshold_value)}",
        annotation_position="bottom right",
        annotation_font=dict(size=10, color=COLORS["amber"]),
    )
    cash_figure.update_yaxes(tickformat="€,.0s")
    style_figure(cash_figure, height=355)

    bridge_figure = make_subplots(specs=[[{"secondary_y": True}]])
    bridge_figure.add_trace(go.Bar(x=weeks, y=collections, name="Collections", marker_color=COLORS["accent"]), secondary_y=False)
    for values, name, color in [
        (-payroll, "Payroll", COLORS["red"]),
        (-suppliers, "Suppliers", COLORS["amber"]),
        (-tax, "Tax", COLORS["purple"]),
        (-capex, "Capex", COLORS["blue"]),
    ]:
        bridge_figure.add_trace(go.Bar(x=weeks, y=values, name=name, marker_color=color), secondary_y=False)
    bridge_figure.add_trace(go.Scatter(x=weeks, y=closing, name="Closing cash", line=dict(color=COLORS["ink"], width=2)), secondary_y=True)
    bridge_figure.update_layout(barmode="relative")
    style_figure(bridge_figure, height=330)
    bridge_figure.update_yaxes(tickformat="€,.0s", secondary_y=False)
    bridge_figure.update_yaxes(tickformat="€,.0s", gridcolor="rgba(0,0,0,0)", secondary_y=True)

    minimum_cash = float(closing.min())
    lowest_index = int(closing.idxmin()) if len(closing) else 0
    lowest_week = weeks.loc[lowest_index] if len(weeks) else pd.Timestamp.today()
    headroom = minimum_cash - threshold_value
    funding_need = max(0.0, -headroom)
    kpis = [
        metric_card(
            "Lowest cash week",
            lowest_week.strftime("%d %b"),
            f"Week {lowest_index + 1}",
            tone="warning",
            explanation="The week when the forecast closing cash balance is at its lowest. This is the plan's tightest cash point.",
            formula="Week containing the lowest closing cash balance",
        ),
        metric_card(
            "Minimum cash",
            euro(minimum_cash),
            euro(headroom) + " vs floor",
            tone="positive" if headroom >= 0 else "negative",
            explanation="The smallest closing cash balance expected during the 13-week period.",
            formula="MIN(weekly closing cash)",
        ),
        metric_card(
            "Liquidity headroom",
            euro(headroom),
            "at the low point",
            tone="positive" if headroom >= 0 else "negative",
            explanation="The cash cushion remaining above the safety threshold at the lowest point. A negative number means the forecast falls below the floor.",
            formula="Minimum cash − minimum cash threshold",
        ),
        metric_card(
            "Peak funding need",
            euro(funding_need),
            "modeled requirement",
            tone="negative" if funding_need else "positive",
            explanation="The extra cash or financing needed to keep the forecast at or above the safety threshold.",
            formula="MAX(0, minimum cash threshold − minimum cash)",
        ),
    ]
    conclusion = callout(
        "Liquidity conclusion",
        (
            f"The current 13-week plan stays above the management floor with {euro(headroom)} of minimum headroom."
            if headroom >= 0
            else f"Cash falls below the management floor in week {lowest_index + 1}; the peak modeled funding requirement is {euro(funding_need)}."
        ),
        "info" if headroom >= 0 else "warning",
    )
    table_records = []
    for index in range(len(forecast)):
        table_records.append(
            {
                "week": weeks.iloc[index].strftime("%d %b %Y"),
                "opening_cash": euro(opening.iloc[index]),
                "collections": euro(collections.iloc[index]),
                "payroll": euro(payroll.iloc[index]),
                "suppliers": euro(suppliers.iloc[index]),
                "tax": euro(tax.iloc[index]),
                "capex": euro(capex.iloc[index]),
                "closing_cash": euro(closing.iloc[index]),
            }
        )
    export_frame = forecast.copy()
    for column in export_frame.select_dtypes(include=["datetime64[ns]"]).columns:
        export_frame[column] = export_frame[column].dt.strftime("%Y-%m-%d")
    return cash_figure, bridge_figure, kpis, conclusion, table_records, export_frame.to_dict("records")


@callback(
    Output("liquidity-download", "data"),
    Input("liquidity-export", "n_clicks"),
    State("liquidity-forecast-store", "data"),
    prevent_initial_call=True,
)
def export_liquidity(_: int, records: list[dict] | None):
    frame = pd.DataFrame(records or [])
    return dcc.send_data_frame(frame.to_csv, "13_week_cash_forecast.csv", index=False)
