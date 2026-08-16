"""Forecast diagnostics and walk-forward benchmark credibility view."""

from __future__ import annotations

from functools import lru_cache

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from components.cards import callout, metric_card, status_pill
from components.charts import COLORS, style_figure
from components.data_access import load_dataset
from components.formatting import euro, percent
from components.learning import chart_guide, learning_guide, teaching_callout
from components.tables import data_table
from forecasting import compare_models, complexity_insight


dash.register_page(
    __name__,
    path="/diagnostics",
    name="Model Diagnostics",
    title="NovaPlan | Model Diagnostics",
)


TARGETS = {
    "revenue_eur": ("Revenue", "currency"),
    "utilization": ("Utilization", "percent"),
    "cash_collections_eur": ("Collections", "currency"),
    "ebitda_eur": ("EBITDA", "currency"),
    "closing_cash_eur": ("Closing cash", "currency"),
}

FEATURES = [
    "headcount",
    "billable_share",
    "utilization",
    "working_days",
    "billing_rate_eur",
    "realization_rate",
    "backlog_eur",
    "dso",
    "new_hires",
    "eur_ron",
]


@lru_cache(maxsize=8)
def _backtest(target: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = load_dataset("monthly_kpis").copy()
    feature_columns = [column for column in FEATURES if column in history.columns and column != target]
    comparison, predictions = compare_models(
        history,
        target_column=target,
        feature_columns=feature_columns,
        initial_train_size=36,
    )
    return comparison, predictions


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Forecast governance", className="page-kicker"),
                            html.H1("Complexity has to earn its place"),
                            html.P("Rolling-origin backtests compare interpretable and statistical approaches without shuffling financial time series."),
                        ]
                    ),
                    status_pill("Walk-forward validation", "positive"),
                ],
                className="page-heading",
            ),
            learning_guide(
                "This page checks whether a forecasting method works on months it had not seen before. The goal is dependable decisions, not simply the most complicated model.",
                [
                    (
                        "Choose what to test",
                        "Select revenue, utilization, collections, EBITDA, or closing cash. The models are compared separately for the selected target.",
                    ),
                    (
                        "Understand the test",
                        "Walk-forward validation trains on earlier months, predicts the next unseen month, then moves forward and repeats. This respects time order and avoids learning from the future.",
                    ),
                    (
                        "Read error from two angles",
                        "Use WAPE for scale-free overall error and MAE for a typical error in the target's own unit. Then inspect the charts for turning points, bias, and unstable periods.",
                    ),
                    (
                        "Prefer useful simplicity",
                        "The best model has the lowest WAPE here, but a small numerical gain may not justify a method that is harder to explain, maintain, or challenge.",
                    ),
                ],
                concepts=["Backtest", "Out of sample", "Residual", "MAE", "RMSE", "WAPE", "Directional accuracy"],
                open_by_default=True,
            ),
            html.Div(
                [
                    html.Div("Evaluation target", className="panel-label"),
                    dcc.RadioItems(
                        id="diagnostic-target",
                        options=[{"label": label, "value": key} for key, (label, _) in TARGETS.items()],
                        value="revenue_eur",
                        className="segmented-control",
                        inline=True,
                    ),
                    html.Div(
                        "Pick the business measure you want to forecast. Currency errors are shown in euros; utilization errors are shown as percentage differences.",
                        className="model-note",
                        style={"marginTop": "10px"},
                    ),
                ],
                className="panel",
                style={"marginBottom": "16px"},
            ),
            html.Div(id="diagnostic-kpis", className="metric-grid four"),
            html.Div(
                [
                    teaching_callout(
                        "Forecast error metrics",
                        "An error is actual minus predicted. MAE reports the average absolute miss in the original unit; RMSE gives extra weight to large misses; directional accuracy asks whether the model correctly predicted whether the measure would rise, fall, or stay flat. For MAE and RMSE, lower is better; for directional accuracy, higher is better.",
                        formula="Error = Actual - Predicted; MAE = mean(|Error|); RMSE = square root(mean(Error²))",
                        example="Errors of +€10k and -€20k produce an MAE of €15k because direction is removed before averaging.",
                    ),
                    teaching_callout(
                        "WAPE (weighted absolute percentage error)",
                        "WAPE expresses total absolute forecast error as a share of total actual volume. This makes models easier to compare across targets of different sizes. A WAPE of 6% means the absolute misses together equal 6% of the actual total; it does not mean every month missed by exactly 6%.",
                        formula="WAPE = sum(|Actual - Predicted|) / sum(|Actual|) x 100",
                        example="If actual values total €1,000k and absolute errors total €60k, WAPE is 6%.",
                    ),
                ],
                className="content-grid equal",
                style={"marginBottom": "16px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Actual vs predicted"), html.P("Does the best model track turning points out of sample?")], className="panel-header"),
                            chart_guide("The dark line is what happened and the colored line is the best model's prediction. Smaller gaps are better; repeated gaps on the same side suggest bias, while missed peaks or dips reveal turning-point risk."),
                            dcc.Loading(dcc.Graph(id="diagnostic-actual-chart", config={"displayModeBar": False}), type="circle"),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.Div([html.H3("Model comparison"), html.P("Lower forecast error is better")], className="panel-header"),
                            data_table(
                                "diagnostic-table",
                                [],
                                columns=[
                                    {"name": "Model", "id": "model"},
                                    {"name": "MAE", "id": "mae"},
                                    {"name": "RMSE", "id": "rmse"},
                                    {"name": "WAPE", "id": "wape"},
                                    {"name": "Direction", "id": "direction"},
                                ],
                                page_size=6,
                            ),
                            html.Div(
                                "Start with WAPE because this table ranks models from lowest WAPE to highest, using MAE as the tie-breaker. Then compare RMSE for large misses and Direction for turning-point performance.",
                                className="model-note",
                                style={"marginTop": "12px"},
                            ),
                        ],
                        className="panel",
                    ),
                ],
                className="content-grid",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Residual distribution"), html.P("Are errors centered, or systematically biased?")], className="panel-header"),
                            chart_guide("A residual is actual minus predicted. Bars close to zero are better. Positive values mean the model underpredicted; negative values mean it overpredicted. A narrow, balanced shape around zero suggests less bias and variability."),
                            dcc.Graph(id="diagnostic-residual-chart", config={"displayModeBar": False}),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.Div([html.H3("Forecast error over time"), html.P("Is performance stable through stress and recovery?")], className="panel-header"),
                            chart_guide("Each bar is actual minus predicted for one test month. Above zero means an underforecast and below zero an overforecast. Look for long runs on one side or unusually tall bars during specific periods."),
                            dcc.Graph(id="diagnostic-error-chart", config={"displayModeBar": False}),
                        ],
                        className="panel",
                    ),
                ],
                className="content-grid equal",
            ),
            html.Div(id="diagnostic-conclusion"),
            html.Div(
                "Higher complexity is only preferred when it produces meaningful out-of-sample improvement. Statistical fit does not replace business judgment, and historical relationships may change.",
                className="disclaimer",
            ),
        ]
    )


@callback(
    Output("diagnostic-actual-chart", "figure"),
    Output("diagnostic-residual-chart", "figure"),
    Output("diagnostic-error-chart", "figure"),
    Output("diagnostic-table", "data"),
    Output("diagnostic-kpis", "children"),
    Output("diagnostic-conclusion", "children"),
    Input("diagnostic-target", "value"),
)
def update_diagnostics(target: str):
    target = target if target in TARGETS else "revenue_eur"
    label, value_type = TARGETS[target]
    comparison, predictions = _backtest(target)
    best_name = str(comparison.iloc[0]["Model"])
    best = predictions[predictions["Model"] == best_name].copy()
    date_col = next((column for column in ["date", "month", "forecast_date"] if column in best), None)
    dates = pd.to_datetime(best[date_col]) if date_col else pd.RangeIndex(len(best))
    actual_col = next((column for column in ["actual", "y_true"] if column in best), "actual")
    predicted_col = next((column for column in ["predicted", "prediction", "y_pred"] if column in best), "predicted")
    actual = pd.to_numeric(best[actual_col], errors="coerce")
    predicted = pd.to_numeric(best[predicted_col], errors="coerce")
    residual = actual - predicted

    actual_figure = go.Figure()
    actual_figure.add_trace(go.Scatter(x=dates, y=actual, name="Actual", mode="lines+markers", line=dict(color=COLORS["ink"], width=2), marker=dict(size=4)))
    actual_figure.add_trace(go.Scatter(x=dates, y=predicted, name=f"Predicted · {best_name}", mode="lines", line=dict(color=COLORS["accent"], width=2.5)))
    if value_type == "currency":
        actual_figure.update_yaxes(tickformat="€,.0s")
    else:
        actual_figure.update_yaxes(tickformat=".0%")
    style_figure(actual_figure, height=345)

    residual_figure = go.Figure(go.Histogram(x=residual, nbinsx=18, marker_color=COLORS["blue"], opacity=.82))
    residual_figure.add_vline(x=0, line_color=COLORS["ink"], line_width=1)
    if value_type == "currency":
        residual_figure.update_xaxes(tickformat="€,.0s")
    else:
        residual_figure.update_xaxes(tickformat=".1%")
    style_figure(residual_figure, height=300, hovermode="closest")

    error_figure = go.Figure(
        go.Bar(
            x=dates,
            y=residual,
            name="Forecast error",
            marker_color=[COLORS["red"] if value < 0 else COLORS["accent"] for value in residual],
        )
    )
    error_figure.add_hline(y=0, line_color="#A9B3B1", line_width=1)
    if value_type == "currency":
        error_figure.update_yaxes(tickformat="€,.0s")
    else:
        error_figure.update_yaxes(tickformat=".1%")
    style_figure(error_figure, height=300, hovermode="x")

    def metric_format(value: float) -> str:
        return euro(value) if value_type == "currency" else percent(value)

    table_records = [
        {
            "model": row["Model"],
            "mae": metric_format(float(row["MAE"])),
            "rmse": metric_format(float(row["RMSE"])),
            "wape": percent(float(row["WAPE"])),
            "direction": percent(float(row["Directional Accuracy"])),
        }
        for _, row in comparison.iterrows()
    ]
    best_row = comparison.iloc[0]
    kpis = [
        metric_card(
            "Best model",
            best_name,
            "lowest WAPE",
            tone="positive",
            explanation="The forecasting method with the lowest out-of-sample WAPE for the selected target. The name identifies a method, not a guarantee that it will remain best in the future.",
            formula="Model with minimum WAPE; MAE breaks a tie",
        ),
        metric_card(
            "MAE",
            metric_format(float(best_row["MAE"])),
            label,
            explanation="Mean absolute error is the average size of the model's miss, ignoring whether it predicted too high or too low. It stays in the same unit as the selected target.",
            formula="MAE = mean(|Actual - Predicted|)",
        ),
        metric_card(
            "WAPE",
            percent(float(best_row["WAPE"])),
            "out-of-sample",
            tone="positive" if float(best_row["WAPE"]) < .08 else "warning",
            explanation="Weighted absolute percentage error compares all absolute misses with the total actual volume in the test period. Lower is better and the percentage is easy to compare across differently sized targets.",
            formula="WAPE = sum(|Actual - Predicted|) / sum(|Actual|) x 100",
        ),
        metric_card(
            "Directional accuracy",
            percent(float(best_row["Directional Accuracy"])),
            "turning-point hit rate",
            explanation="The share of tested changes for which the model correctly predicted whether the target would rise, fall, or remain flat versus the previous actual value.",
            formula="Correctly predicted change directions / All tested change directions x 100",
        ),
    ]
    insight = complexity_insight(comparison)
    conclusion = callout("Model-selection conclusion", insight, "info")
    return actual_figure, residual_figure, error_figure, table_records, kpis, conclusion
