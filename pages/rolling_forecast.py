"""Driver-based 18-month rolling forecast with transparent management overlays."""

from __future__ import annotations

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html, no_update

from components.audit import append_audit_entry
from components.cards import callout, metric_card, status_pill
from components.charts import COLORS, empty_figure, style_figure
from components.controls import number_input
from components.data_access import load_dataset
from components.formatting import euro, number, percent
from components.learning import chart_guide, learning_guide, teaching_callout
from components.page_utils import first_column, first_date_column
from models.forecast import build_monthly_forecast


dash.register_page(
    __name__,
    path="/rolling-forecast",
    name="Rolling Forecast",
    title="NovaPlan | Rolling Forecast",
)


METRICS = {
    "revenue_eur": ("Revenue", "currency"),
    "ebitda_eur": ("EBITDA", "currency"),
    "ebitda_margin": ("EBITDA margin", "percent"),
    "closing_cash_eur": ("Cash", "currency"),
    "accounts_receivable_eur": ("Accounts receivable", "currency"),
    "dso": ("DSO", "days"),
    "headcount": ("Headcount", "number"),
    "utilization": ("Utilization", "percent"),
}


def _formatted(value: float, value_type: str) -> str:
    if value_type == "currency":
        return euro(value)
    if value_type == "percent":
        return percent(value)
    if value_type == "days":
        return f"{value:.0f} days"
    return number(value)


def layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="rolling-export-store"),
            dcc.Download(id="rolling-download"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Driver-based outlook", className="page-kicker"),
                            html.H1("18-month rolling forecast"),
                            html.P("Separate observed performance, the model baseline, and management judgment without losing the audit trail."),
                        ]
                    ),
                    html.Div(
                        [
                            status_pill("Actuals through Dec 2025", "positive"),
                            html.Button("Export forecast", id="rolling-export", className="button secondary"),
                        ],
                        className="page-heading-actions",
                    ),
                ],
                className="page-heading",
            ),
            learning_guide(
                "Use this page to see what has happened, what the model expects next, and where management has added its own judgment.",
                [
                    ("Choose a metric", "Select revenue, cash, headcount, or another measure to study."),
                    ("Read the three lines", "Compare recorded actuals with the untouched model baseline and the adjusted final forecast."),
                    ("Explain any adjustment", "Enter a percentage only when you know something the model does not, then record the reason."),
                ],
                concepts=["Actual", "Model baseline", "Management adjustment", "Final forecast"],
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("View metric", className="panel-label"),
                            dcc.RadioItems(
                                id="rolling-metric",
                                options=[{"label": label, "value": key} for key, (label, _) in METRICS.items()],
                                value="revenue_eur",
                                className="segmented-control",
                                inline=True,
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(id="rolling-kpis", className="metric-grid four"),
                ]
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Actual, baseline, and final forecast"), html.P("How much of the outlook comes from the model versus management judgment?")], className="panel-header"),
                            chart_guide("Follow gray for recorded actuals, teal for the model baseline, and dashed amber for the adjusted forecast. The dotted marker is where forecasting begins."),
                            dcc.Loading(dcc.Graph(id="rolling-chart", figure=empty_figure("Building the forecast…"), config={"displayModeBar": False}), type="circle"),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H3("Management overlay", className="controls-title"),
                            html.P("Apply a transparent adjustment to the selected metric. The baseline remains visible.", className="controls-description"),
                            teaching_callout(
                                "Model baseline vs management adjustment",
                                "The baseline is the model's automatic estimate. An adjustment is a separate judgment added by management; it never rewrites the baseline.",
                                formula="Final forecast = Model baseline × (1 + adjustment %)",
                                example="A €100 baseline with a +5% adjustment becomes €105.",
                            ),
                            number_input(
                                "rolling-adjustment",
                                "Adjustment",
                                0,
                                minimum=-30,
                                maximum=30,
                                step=0.5,
                                suffix="%",
                                hint="Raise it to increase every forecast month; lower it to reduce every forecast month. Zero keeps the model unchanged.",
                            ),
                            html.Div(
                                [
                                    html.Label("Adjustment rationale"),
                                    dcc.Textarea(
                                        id="rolling-rationale",
                                        placeholder="What information is not captured in the model baseline?",
                                    ),
                                ],
                                className="field",
                                style={"marginTop": "13px"},
                            ),
                            html.Button("Save to audit log", id="rolling-save", className="button full"),
                            html.Div(id="rolling-save-message"),
                            html.Div(
                                "Management adjustments affect the displayed final forecast only; they never overwrite the model baseline.",
                                className="model-note",
                                style={"marginTop": "14px"},
                            ),
                        ],
                        className="controls-panel",
                    ),
                ],
                className="content-grid",
            ),
            html.Div(id="rolling-conclusion"),
        ]
    )


@callback(
    Output("rolling-chart", "figure"),
    Output("rolling-kpis", "children"),
    Output("rolling-conclusion", "children"),
    Output("rolling-export-store", "data"),
    Input("rolling-metric", "value"),
    Input("rolling-adjustment", "value"),
)
def update_rolling_forecast(metric: str, adjustment: float):
    history = load_dataset("monthly_kpis")
    forecast = build_monthly_forecast(history, months=18)
    metric = metric if metric in METRICS else "revenue_eur"
    label, value_type = METRICS[metric]
    adjustment_rate = (adjustment or 0) / 100

    actual_dates = first_date_column(history.tail(24), ["month", "date"])
    forecast_dates = first_date_column(forecast, ["month", "date"])
    actual = first_column(history.tail(24), [metric])
    baseline = first_column(forecast, [metric])
    final = baseline * (1 + adjustment_rate)

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=actual_dates,
            y=actual,
            name="Actual",
            mode="lines",
            line=dict(color="#91A3A4", width=2),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast_dates,
            y=baseline,
            name="Model baseline",
            mode="lines",
            line=dict(color=COLORS["accent"], width=2.5),
        )
    )
    if abs(adjustment_rate) > 1e-9:
        figure.add_trace(
            go.Scatter(
                x=forecast_dates,
                y=final,
                name="Final forecast",
                mode="lines",
                line=dict(color=COLORS["amber"], width=2.2, dash="dash"),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=list(forecast_dates) + list(forecast_dates.iloc[::-1]),
                y=list(final) + list(baseline.iloc[::-1]),
                name="Management overlay",
                fill="toself",
                fillcolor="rgba(199,137,59,.09)",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    if len(forecast_dates):
        marker_date = forecast_dates.iloc[0]
        figure.add_vline(x=marker_date, line_dash="dot", line_color="#929FA1", line_width=1)
        figure.add_annotation(
            x=marker_date,
            y=1.04,
            xref="x",
            yref="paper",
            text="FORECAST START",
            showarrow=False,
            xanchor="left",
            font=dict(size=9, color=COLORS["muted"]),
        )
    if value_type == "currency":
        figure.update_yaxes(tickformat="€,.0s")
    elif value_type == "percent":
        figure.update_yaxes(tickformat=".0%")
    elif value_type == "days":
        figure.update_yaxes(ticksuffix=" days")
    style_figure(figure, height=420)

    baseline_total = baseline.sum() if value_type == "currency" and metric in {"revenue_eur", "ebitda_eur"} else baseline.iloc[-1]
    final_total = final.sum() if value_type == "currency" and metric in {"revenue_eur", "ebitda_eur"} else final.iloc[-1]
    actual_last = float(actual.iloc[-1])
    low_point = float(final.min())
    kpis = [
        metric_card(
            "Latest actual",
            _formatted(actual_last, value_type),
            label,
            explanation="The most recent recorded result for the selected metric. It is observed data, not a prediction.",
            formula="Latest actual = value in the most recent closed month",
        ),
        metric_card(
            "Model baseline",
            _formatted(float(baseline_total), value_type),
            "18-month total" if metric in {"revenue_eur", "ebitda_eur"} else "month 18",
            explanation="The model's forecast before management adds any manual judgment.",
            formula=(
                "Baseline total = sum of the 18 forecast months"
                if metric in {"revenue_eur", "ebitda_eur"}
                else "Baseline = model value in forecast month 18"
            ),
        ),
        metric_card(
            "Management adjustment",
            f"{adjustment or 0:+.1f}%",
            "visible overlay",
            tone="warning" if adjustment else "neutral",
            explanation="The percentage entered by management to reflect information not captured by the model.",
            formula="Adjustment amount = Model baseline × adjustment %",
        ),
        metric_card(
            "Final forecast",
            _formatted(float(final_total), value_type),
            _formatted(float(final_total - baseline_total), value_type) + " vs model",
            tone="positive" if final_total >= baseline_total else "negative",
            explanation="The planning view after the visible management adjustment is applied to the model baseline.",
            formula="Final forecast = Model baseline × (1 + adjustment %)",
        ),
    ]
    conclusion = callout(
        "Forecast interpretation",
        f"The final {label.lower()} view is {_formatted(float(final_total - baseline_total), value_type)} versus the model baseline. The adjustment is separately identified and requires a rationale before it enters the audit log.",
        "info" if adjustment_rate >= 0 else "warning",
    )

    export = pd.DataFrame(
        {
            "month": forecast_dates.dt.strftime("%Y-%m-%d"),
            "metric": label,
            "model_baseline": baseline,
            "management_adjustment_pct": adjustment or 0,
            "final_forecast": final,
        }
    )
    return figure, kpis, conclusion, export.to_dict("records")


@callback(
    Output("rolling-save-message", "children"),
    Output("global-audit-version", "data", allow_duplicate=True),
    Input("rolling-save", "n_clicks"),
    State("rolling-metric", "value"),
    State("rolling-adjustment", "value"),
    State("rolling-rationale", "value"),
    State("global-audit-version", "data"),
    prevent_initial_call=True,
)
def save_management_overlay(
    _: int,
    metric: str,
    adjustment: float,
    rationale: str | None,
    version: int,
):
    if not rationale or not rationale.strip():
        return html.Div("Add a rationale before saving.", className="toast", style={"color": COLORS["red"], "background": "#FAECEA"}), no_update
    append_audit_entry("Rolling Forecast", METRICS[metric][0], 0, adjustment or 0, rationale)
    return html.Div("Management adjustment saved to the audit log.", className="toast"), (version or 0) + 1


@callback(
    Output("rolling-download", "data"),
    Input("rolling-export", "n_clicks"),
    State("rolling-export-store", "data"),
    prevent_initial_call=True,
)
def export_rolling_forecast(_: int, records: list[dict] | None):
    return dcc.send_data_frame(pd.DataFrame(records or []).to_csv, "forecast.csv", index=False)
