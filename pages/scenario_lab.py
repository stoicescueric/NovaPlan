"""Interactive scenario planning with a transparent base-case comparison."""

from __future__ import annotations

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html, no_update

from components.audit import append_audit_entry
from components.cards import callout, metric_card, status_pill
from components.charts import COLORS, empty_figure, style_figure
from components.controls import dropdown, number_input
from components.data_access import load_dataset
from components.formatting import euro, number, percent, pp
from components.learning import chart_guide, learning_guide, teaching_callout
from components.page_utils import first_column, first_date_column, summary_value
from components.tables import data_table
from models.scenarios import run_scenario


dash.register_page(
    __name__,
    path="/scenario-lab",
    name="Scenario Lab",
    title="NovaPlan | Scenario Lab",
)


SCENARIOS = [
    "Base",
    "Upside",
    "Downside",
    "Hiring Expansion",
    "Collections Improvement",
    "Pricing Initiative",
    "2026 Expansion Decision",
    "Risk Case",
    "Mitigation Case",
    "Custom Scenario",
]


def layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="scenario-export-store"),
            dcc.Download(id="scenario-download"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Management decision lab", className="page-kicker"),
                            html.H1("Can NovaBridge hire 40 consultants and protect liquidity?"),
                            html.P("Test an operating plan, see its profit and cash consequences, then identify the assumptions that make or break it."),
                        ]
                    ),
                    html.Div(
                        [
                            status_pill("Preloaded partner demo", "positive"),
                            html.Button("Export scenario", id="scenario-export", className="button secondary"),
                        ],
                        className="page-heading-actions",
                    ),
                ],
                className="page-heading",
            ),
            learning_guide(
                "Use this page to test a decision without treating the result as the one true future.",
                [
                    ("Choose a starting case", "Pick a preset scenario whose assumptions are closest to the decision you want to test."),
                    ("Change one assumption", "Move an input up or down and watch how profit and cash respond."),
                    ("Check the cash floor", "Compare the scenario with Base, then look for the lowest cash point and any funding need."),
                ],
                concepts=["Base case", "Scenario", "EBITDA", "Liquidity floor", "Headroom"],
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Scenario assumptions", className="controls-title"),
                            html.P("Choose a preset, then layer explicit changes on top. Zero means no incremental change to the preset.", className="controls-description"),
                            teaching_callout(
                                "Scenario vs forecast",
                                "A forecast is the current best estimate of what will happen. A scenario is a deliberate what-if used to learn how a decision or risk could change the result.",
                                formula="Scenario delta = Scenario result − Base result",
                                example="If scenario cash is €8m and Base cash is €10m, the delta is −€2m.",
                            ),
                            html.Div(
                                [
                                    dropdown(
                                        "scenario-preset",
                                        "Scenario",
                                        SCENARIOS,
                                        "2026 Expansion Decision",
                                        hint="A preset is a ready-made what-if. Changing it replaces the starting assumptions; the fields below add changes on top.",
                                    ),
                                    number_input(
                                        "sc-demand", "Revenue demand", 0, minimum=-25, maximum=25, step=1, suffix="%",
                                        hint="Expected customer demand. Higher demand usually raises revenue; lower demand reduces it.",
                                    ),
                                    number_input(
                                        "sc-utilization", "Utilization", 0, minimum=-15, maximum=15, step=0.5, suffix="pp",
                                        hint="Change in the share of staff time that is billable. Higher values usually raise revenue and EBITDA.",
                                    ),
                                    number_input(
                                        "sc-rate", "Billing rate", 0, minimum=-10, maximum=20, step=0.5, suffix="%",
                                        hint="Change in the price billed to clients. Higher rates usually raise revenue, if demand holds.",
                                    ),
                                    number_input(
                                        "sc-hires", "Additional hires", 0, minimum=0, maximum=80, step=5, suffix="people",
                                        hint="Extra full-time employees. More hires add capacity but increase salary, recruiting, and equipment costs first.",
                                    ),
                                    number_input(
                                        "sc-attrition", "Attrition", 0, minimum=-5, maximum=10, step=0.5, suffix="pp",
                                        hint="Change in the annual employee departure rate. Higher attrition reduces available staff and can limit growth.",
                                    ),
                                    number_input(
                                        "sc-salary", "Salary inflation", 0, minimum=-5, maximum=15, step=0.5, suffix="pp",
                                        hint="Extra annual pay growth. Higher values increase payroll cost and usually reduce EBITDA and cash.",
                                    ),
                                    number_input(
                                        "sc-dso", "DSO change", 0, minimum=-25, maximum=30, step=1, suffix="days",
                                        hint="Change in average customer payment time. Higher DSO means slower collection and usually less cash.",
                                    ),
                                    number_input(
                                        "sc-dpo", "DPO change", 0, minimum=-15, maximum=20, step=1, suffix="days",
                                        hint="Change in average supplier payment time. Higher DPO delays payment and preserves cash temporarily.",
                                    ),
                                    number_input(
                                        "sc-fx", "EUR/RON", 0, minimum=-8, maximum=8, step=0.5, suffix="%",
                                        hint="Change in Romanian lei per euro. A higher rate lowers RON salary costs when reported in euros in this model.",
                                    ),
                                    number_input(
                                        "sc-capex", "Capex", 0, minimum=-50, maximum=100, step=5, suffix="%",
                                        hint="Change in spending on long-term assets. Higher capex uses more cash now.",
                                    ),
                                    number_input(
                                        "sc-opex", "Discretionary OPEX", 0, minimum=-30, maximum=30, step=1, suffix="%",
                                        hint="Change in controllable operating costs. Higher OPEX lowers EBITDA and cash.",
                                    ),
                                ],
                                className="controls-grid one",
                            ),
                            html.Div(
                                [
                                    html.Label("Decision rationale"),
                                    dcc.Textarea(id="scenario-rationale", placeholder="Why is management testing this case?"),
                                ],
                                className="field",
                                style={"marginTop": "14px"},
                            ),
                            html.Button("Save scenario to audit log", id="scenario-save", className="button full"),
                            html.Div(id="scenario-save-message"),
                        ],
                        className="controls-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id="scenario-kpis", className="metric-grid five"),
                            html.Div(
                                [
                                    html.Div(
                                        [html.H3("Liquidity path: Base vs scenario"), html.P("Does the operating decision create a temporary funding gap?")],
                                        className="panel-header",
                                    ),
                                    chart_guide("Compare the gray Base line with the teal scenario line. The lowest point matters most; falling below the dashed €3m floor signals a liquidity gap."),
                                    dcc.Loading(dcc.Graph(id="scenario-cash-chart", figure=empty_figure("Calculating scenario…"), config={"displayModeBar": False}), type="circle"),
                                ],
                                className="panel",
                            ),
                            html.Div(id="scenario-conclusion", style={"marginTop": "14px"}),
                        ]
                    ),
                ],
                className="content-grid sidebar-layout",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Profit vs cash trade-off"), html.P("Growth can be economically attractive before it becomes cash generative.")], className="panel-header"),
                            chart_guide("For each metric, compare the gray Base bar with the teal scenario bar. Revenue and EBITDA can improve even while cash falls."),
                            dcc.Graph(id="scenario-tradeoff-chart", figure=empty_figure(), config={"displayModeBar": False}),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.Div([html.H3("Decision scorecard"), html.P("Scenario outputs and deltas to Base")], className="panel-header"),
                            data_table(
                                "scenario-table",
                                [],
                                columns=[
                                    {"name": "Metric", "id": "metric"},
                                    {"name": "Base", "id": "base"},
                                    {"name": "Scenario", "id": "scenario"},
                                    {"name": "Δ vs Base", "id": "delta"},
                                ],
                                page_size=10,
                            ),
                        ],
                        className="panel",
                    ),
                ],
                className="content-grid equal",
            ),
        ]
    )


@callback(
    Output("scenario-cash-chart", "figure"),
    Output("scenario-tradeoff-chart", "figure"),
    Output("scenario-kpis", "children"),
    Output("scenario-conclusion", "children"),
    Output("scenario-table", "data"),
    Output("scenario-export-store", "data"),
    Input("scenario-preset", "value"),
    Input("sc-demand", "value"),
    Input("sc-utilization", "value"),
    Input("sc-rate", "value"),
    Input("sc-hires", "value"),
    Input("sc-attrition", "value"),
    Input("sc-salary", "value"),
    Input("sc-dso", "value"),
    Input("sc-dpo", "value"),
    Input("sc-fx", "value"),
    Input("sc-capex", "value"),
    Input("sc-opex", "value"),
)
def update_scenario(
    preset: str,
    demand: float,
    utilization: float,
    rate: float,
    hires: float,
    attrition: float,
    salary: float,
    dso: float,
    dpo: float,
    fx: float,
    capex: float,
    opex: float,
):
    history = load_dataset("monthly_kpis")
    candidate_overrides = {
        "_delta_mode": True,
        "revenue_demand_change_pct": (demand or 0) / 100,
        "utilization_delta_pp": (utilization or 0) / 100,
        "billing_rate_change_pct": (rate or 0) / 100,
        "incremental_hires": int(hires or 0),
        "attrition_delta_pp": (attrition or 0) / 100,
        "salary_inflation_delta_pp": (salary or 0) / 100,
        "dso_delta_days": dso or 0,
        "dpo_delta_days": dpo or 0,
        "eur_ron_change_pct": (fx or 0) / 100,
        "capex_change_pct": (capex or 0) / 100,
        "discretionary_opex_change_pct": (opex or 0) / 100,
    }
    overrides = candidate_overrides
    model_preset = "Custom" if preset == "Custom Scenario" else (preset or "Base")
    base = run_scenario(history, "Base")
    scenario = run_scenario(history, model_preset, overrides)
    base_summary = base.get("summary", {})
    scenario_summary = scenario.get("summary", {})
    base_forecast = base["forecast"]
    scenario_forecast = scenario["forecast"]

    base_revenue = summary_value(base_summary, "revenue_eur", "total_revenue_eur", "forecast_revenue_eur", default=first_column(base_forecast, ["revenue_eur"]).sum())
    scenario_revenue = summary_value(scenario_summary, "revenue_eur", "total_revenue_eur", "forecast_revenue_eur", default=first_column(scenario_forecast, ["revenue_eur"]).sum())
    base_ebitda = summary_value(base_summary, "ebitda_eur", "total_ebitda_eur", default=first_column(base_forecast, ["ebitda_eur"]).sum())
    scenario_ebitda = summary_value(scenario_summary, "ebitda_eur", "total_ebitda_eur", default=first_column(scenario_forecast, ["ebitda_eur"]).sum())
    base_cash_series = first_column(base_forecast, ["closing_cash_eur", "cash_eur"])
    scenario_cash_series = first_column(scenario_forecast, ["closing_cash_eur", "cash_eur"])
    base_year_end_cash = summary_value(base_summary, "year_end_cash_eur", "closing_cash_eur", default=base_cash_series.iloc[-1])
    scenario_year_end_cash = summary_value(scenario_summary, "year_end_cash_eur", "closing_cash_eur", default=scenario_cash_series.iloc[-1])
    base_min_cash = summary_value(base_summary, "minimum_cash_eur", "min_cash_eur", default=base_cash_series.min())
    scenario_min_cash = summary_value(scenario_summary, "minimum_cash_eur", "min_cash_eur", default=scenario_cash_series.min())
    funding = max(0.0, 3_000_000 - scenario_min_cash)

    dates = first_date_column(scenario_forecast, ["month", "date"])
    cash_figure = go.Figure()
    cash_figure.add_trace(go.Scatter(x=dates, y=base_cash_series, name="Base", line=dict(color="#9BAAAA", width=2)))
    cash_figure.add_trace(
        go.Scatter(
            x=dates,
            y=scenario_cash_series,
            name=preset,
            line=dict(color=COLORS["accent"], width=3),
            fill="tonexty",
            fillcolor="rgba(22,112,111,.055)",
        )
    )
    cash_figure.add_hline(y=3_000_000, line_dash="dash", line_color=COLORS["amber"], annotation_text="€3m floor", annotation_position="bottom right")
    cash_figure.update_yaxes(tickformat="€,.0s")
    style_figure(cash_figure, height=370)

    tradeoff = go.Figure()
    categories = ["Revenue", "EBITDA", "Year-end cash", "Minimum cash"]
    base_values = [base_revenue, base_ebitda, base_year_end_cash, base_min_cash]
    scenario_values = [scenario_revenue, scenario_ebitda, scenario_year_end_cash, scenario_min_cash]
    tradeoff.add_trace(go.Bar(x=categories, y=base_values, name="Base", marker_color="#B8C4C2"))
    tradeoff.add_trace(go.Bar(x=categories, y=scenario_values, name=preset, marker_color=COLORS["accent"]))
    tradeoff.update_layout(barmode="group")
    tradeoff.update_yaxes(tickformat="€,.0s")
    style_figure(tradeoff, height=330, hovermode="x")

    margin = scenario_ebitda / scenario_revenue if scenario_revenue else 0
    utilization_series = first_column(scenario_forecast, ["utilization"])
    dso_series = first_column(scenario_forecast, ["dso"])
    headcount_series = first_column(scenario_forecast, ["headcount"])
    kpis = [
        metric_card(
            "Δ Revenue",
            euro(scenario_revenue - base_revenue),
            "vs Base",
            tone="positive" if scenario_revenue >= base_revenue else "negative",
            explanation="How much total forecast revenue changes in this scenario compared with the Base case.",
            formula="Δ Revenue = Scenario revenue − Base revenue",
        ),
        metric_card(
            "Δ EBITDA",
            euro(scenario_ebitda - base_ebitda),
            percent(margin) + " margin",
            tone="positive" if scenario_ebitda >= base_ebitda else "negative",
            explanation="How much operating profit before interest, tax, depreciation, and amortization changes versus Base.",
            formula="Δ EBITDA = Scenario EBITDA − Base EBITDA",
        ),
        metric_card(
            "Δ Year-end cash",
            euro(scenario_year_end_cash - base_year_end_cash),
            "vs Base",
            tone="positive" if scenario_year_end_cash >= base_year_end_cash else "negative",
            explanation="The difference between scenario cash and Base cash at the end of the forecast.",
            formula="Δ Year-end cash = Scenario year-end cash − Base year-end cash",
        ),
        metric_card(
            "Minimum cash",
            euro(scenario_min_cash),
            euro(scenario_min_cash - 3_000_000) + " headroom",
            tone="positive" if scenario_min_cash >= 3_000_000 else "negative",
            explanation="The lowest monthly closing cash balance in the scenario. This reveals temporary shortages that year-end cash can hide.",
            formula="Minimum cash = lowest monthly closing cash",
        ),
        metric_card(
            "Funding need",
            euro(funding),
            "peak modeled gap",
            tone="negative" if funding else "positive",
            explanation="Extra financing needed to keep cash at or above the €3m safety floor.",
            formula="Funding need = max(€3m − Minimum cash, €0)",
        ),
    ]

    risk_driver = "collections and utilization" if (dso or 0) > 0 or (utilization or 0) < 0 else "ramp-up timing and working capital"
    if scenario_ebitda > base_ebitda and scenario_min_cash < base_min_cash:
        conclusion_text = (
            f"{preset} is EBITDA-accretive by {euro(scenario_ebitda - base_ebitda)} but reduces minimum cash by "
            f"{euro(base_min_cash - scenario_min_cash)}. The plan’s near-term risk is concentrated in {risk_driver}."
        )
    elif scenario_min_cash >= 3_000_000:
        conclusion_text = f"{preset} preserves the €3m liquidity floor, with {euro(scenario_min_cash - 3_000_000)} of minimum headroom."
    else:
        conclusion_text = f"{preset} breaches the liquidity floor and creates a modeled funding requirement of {euro(funding)}."
    conclusion = callout("Decision conclusion", conclusion_text, "info" if scenario_min_cash >= 3_000_000 else "warning")

    rows = [
        ("Revenue", base_revenue, scenario_revenue, "currency"),
        ("EBITDA", base_ebitda, scenario_ebitda, "currency"),
        ("EBITDA margin", base_ebitda / base_revenue if base_revenue else 0, margin, "percent"),
        ("Year-end cash", base_year_end_cash, scenario_year_end_cash, "currency"),
        ("Minimum cash", base_min_cash, scenario_min_cash, "currency"),
        ("Headcount", first_column(base_forecast, ["headcount"]).iloc[-1], headcount_series.iloc[-1], "number"),
        ("DSO", first_column(base_forecast, ["dso"]).iloc[-1], dso_series.iloc[-1], "days"),
        ("Utilization", first_column(base_forecast, ["utilization"]).mean(), utilization_series.mean(), "percent"),
    ]

    def format_value(value: float, kind: str) -> str:
        if kind == "currency":
            return euro(value)
        if kind == "percent":
            return percent(value)
        if kind == "days":
            return f"{value:.1f} days"
        return number(value)

    table = [
        {
            "metric": name,
            "base": format_value(base_value, kind),
            "scenario": format_value(scenario_value, kind),
            "delta": (pp(scenario_value - base_value) if kind == "percent" else format_value(scenario_value - base_value, kind)),
        }
        for name, base_value, scenario_value, kind in rows
    ]
    export = pd.DataFrame(
        {
            "month": dates.dt.strftime("%Y-%m-%d"),
            "scenario": preset,
            "base_revenue_eur": first_column(base_forecast, ["revenue_eur"]),
            "scenario_revenue_eur": first_column(scenario_forecast, ["revenue_eur"]),
            "base_ebitda_eur": first_column(base_forecast, ["ebitda_eur"]),
            "scenario_ebitda_eur": first_column(scenario_forecast, ["ebitda_eur"]),
            "base_closing_cash_eur": base_cash_series,
            "scenario_closing_cash_eur": scenario_cash_series,
        }
    )
    return cash_figure, tradeoff, kpis, conclusion, table, export.to_dict("records")


@callback(
    Output("scenario-save-message", "children"),
    Output("global-audit-version", "data", allow_duplicate=True),
    Input("scenario-save", "n_clicks"),
    State("scenario-preset", "value"),
    State("scenario-rationale", "value"),
    State("sc-demand", "value"),
    State("sc-utilization", "value"),
    State("sc-rate", "value"),
    State("sc-hires", "value"),
    State("sc-dso", "value"),
    State("global-audit-version", "data"),
    prevent_initial_call=True,
)
def save_scenario(
    _: int,
    preset: str,
    rationale: str | None,
    demand: float,
    utilization: float,
    rate: float,
    hires: float,
    dso: float,
    version: int,
):
    if not rationale or not rationale.strip():
        return html.Div("Add a decision rationale before saving.", className="toast", style={"color": COLORS["red"], "background": "#FAECEA"}), no_update
    changes = {
        "revenue_demand_change_pct": demand or 0,
        "utilization_delta_pp": utilization or 0,
        "billing_rate_change_pct": rate or 0,
        "incremental_hires": hires or 0,
        "dso_delta_days": dso or 0,
    }
    for variable, value in changes.items():
        if value:
            append_audit_entry(preset, variable, 0, value, rationale)
    if not any(changes.values()):
        append_audit_entry(preset, "preset_selected", "Base", preset, rationale)
    return html.Div("Scenario assumptions saved to the audit log.", className="toast"), (version or 0) + 1


@callback(
    Output("scenario-download", "data"),
    Input("scenario-export", "n_clicks"),
    State("scenario-export-store", "data"),
    prevent_initial_call=True,
)
def export_scenario(_: int, records: list[dict] | None):
    return dcc.send_data_frame(pd.DataFrame(records or []).to_csv, "scenario_results.csv", index=False)
