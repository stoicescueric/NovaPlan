"""Four-control what-if experiment for the student project."""

from __future__ import annotations

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from components.cards import callout, metric_card
from components.charts import COLORS, style_figure
from components.controls import field
from components.data_access import load_dataset
from components.formatting import euro, number
from models.scenarios import run_scenario


dash.register_page(__name__, path="/what-if", name="What-if Experiment", title="NovaPlan | What-if")


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
            dcc.Store(id="what-if-results"),
            html.Div(
                [
                    html.Div(
                        [
                            html.H1("What happens if we hire more people?"),
                            html.P("Move four assumptions and compare the result with the unchanged base plan."),
                        ]
                    )
                ],
                className="page-heading",
            ),
            html.P(
                [html.Strong("Try this: "), "Start with 40 hires. Then delay customer payments or lower utilization and watch the lowest cash point."],
                className="experiment-note",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Change the assumptions", className="controls-title"),
                            html.P("These four inputs feed the same financial forecast.", className="controls-description"),
                            _slider(
                                "simple-hires",
                                "Extra employees",
                                0,
                                60,
                                5,
                                40,
                                {0: "0", 20: "20", 40: "40", 60: "60"},
                                "Think of adding people to a team. They join little by little over the first 6 months. As each person joins, the company starts paying salary, €3,000 for recruiting and €1,800 for equipment; it then takes 3 months for that person to reach a full share of client work. This does not change the hourly price, utilization or how quickly customers pay.",
                            ),
                            _slider(
                                "simple-utilization",
                                "Utilization change",
                                -5,
                                5,
                                1,
                                0,
                                {-5: "−5 pp", 0: "0", 5: "+5 pp"},
                                "Imagine 100 work hours are available. +5 percentage points means 5 more of those hours can be sold to customers each month, so revenue, operating profit and cash normally rise. This does not add employees, raise the hourly price or make customers pay sooner.",
                            ),
                            _slider(
                                "simple-rate",
                                "Billing-rate change",
                                -5,
                                5,
                                1,
                                0,
                                {-5: "−5%", 0: "0", 5: "+5%"},
                                "This changes the price tag on one client hour for all 18 forecast months. If an hour were €100, +5% would make it €105. It changes revenue, invoices, operating profit and cash, but not employee count, utilization or payment speed.",
                            ),
                            _slider(
                                "simple-dso",
                                "Change in average payment time",
                                -15,
                                20,
                                5,
                                0,
                                {-15: "15d faster", 0: "same", 20: "20d slower"},
                                "The work and operating profit are counted first; the customer’s cash arrives later. +20 days means the company waits 20 extra days, so more invoice money stays unpaid and cash falls. It does not change revenue, operating profit, employee count or price.",
                            ),
                        ],
                        className="controls-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id="what-if-kpis", className="metric-grid four"),
                            html.Div(
                                [
                                    html.Div(
                                        [html.H3("Cash: base plan versus your experiment"), html.P("The dashed line is the chosen €3m cash floor.")],
                                        className="panel-header",
                                    ),
                                    dcc.Graph(id="what-if-chart", config={"displayModeBar": False}),
                                ],
                                className="panel",
                            ),
                            html.Div(id="what-if-conclusion"),
                        ],
                        className="results-stack",
                    ),
                ],
                className="content-grid sidebar-layout",
            ),
        ],
        className="primary-page",
    )


@callback(
    Output("what-if-chart", "figure"),
    Output("what-if-kpis", "children"),
    Output("what-if-conclusion", "children"),
    Output("what-if-results", "data"),
    Input("simple-hires", "value"),
    Input("simple-utilization", "value"),
    Input("simple-rate", "value"),
    Input("simple-dso", "value"),
)
def update_what_if(hires: float | None, utilization: float | None, rate: float | None, dso: float | None):
    hires = 0 if hires is None else int(hires)
    utilization = 0.0 if utilization is None else float(utilization)
    rate = 0.0 if rate is None else float(rate)
    dso = 0.0 if dso is None else float(dso)

    history = load_dataset("monthly_kpis")
    base = run_scenario(history, "Base")
    experiment = run_scenario(
        history,
        "Custom",
        {
            "incremental_hires_total": hires,
            "hire_joining_months": 6,
            "hire_ramp_months": 3,
            "utilization_change_pp": utilization / 100,
            "billing_rate_change_pct": rate / 100,
            "dso_delta_days": dso,
        },
    )
    base_summary = base["summary"]
    result = experiment["summary"]
    base_forecast = base["forecast"]
    experiment_forecast = experiment["forecast"]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=base_forecast["month"],
            y=base_forecast["closing_cash_eur"],
            name="Base plan",
            line=dict(color="#9BAAAA", width=2),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=experiment_forecast["month"],
            y=experiment_forecast["closing_cash_eur"],
            name="Your experiment",
            line=dict(color=COLORS["accent"], width=3),
        )
    )
    figure.add_hline(
        y=3_000_000,
        line_dash="dash",
        line_color=COLORS["amber"],
        annotation_text="Chosen €3m cash floor",
        annotation_position="bottom right",
    )
    figure.update_yaxes(tickprefix="€", tickformat=".3s")
    style_figure(figure, height=380)

    revenue_change = float(result["revenue_eur"] - base_summary["revenue_eur"])
    profit_change = float(result["ebitda_eur"] - base_summary["ebitda_eur"])
    minimum_cash = float(result["minimum_cash_eur"])
    minimum_change = minimum_cash - float(base_summary["minimum_cash_eur"])
    people = float(result["headcount"])

    kpis = [
        metric_card(
            "Revenue change",
            euro(revenue_change),
            "versus base",
            tone="positive" if revenue_change >= 0 else "negative",
            explanation="All revenue earned during the 18-month experiment minus all revenue in the unchanged base plan. It is not the same as customer cash collected.",
        ),
        metric_card(
            "Operating profit change",
            euro(profit_change),
            "EBITDA versus base",
            tone="positive" if profit_change >= 0 else "negative",
            explanation="The 18-month change in revenue left after payroll, contractors and normal operating costs. It is before depreciation, interest and tax, so it is not cash or net income.",
        ),
        metric_card(
            "Lowest cash",
            euro(minimum_cash),
            f"{euro(minimum_change)} vs base",
            tone="positive" if minimum_cash >= 3_000_000 else "negative",
            explanation="The smallest monthly closing cash balance anywhere in your 18-month experiment. The note compares that tightest point with the base plan’s tightest point.",
        ),
        metric_card(
            "Employees at the end",
            number(people),
            f"{hires} extra hires selected",
            explanation="The estimated team size in June 2027 after normal hiring, your extra hires and expected staff departures. It is not simply today’s employees plus the slider value.",
        ),
    ]

    if minimum_cash < 3_000_000:
        message = f"This experiment falls below the chosen €3m cash floor. The lowest cash balance is {euro(minimum_cash)}."
        tone = "warning"
    elif profit_change > 0 and minimum_change < 0:
        message = f"The plan adds {euro(profit_change)} of profit, but the lowest cash point is {euro(abs(minimum_change))} lower while the new employees ramp up."
        tone = "info"
    elif profit_change > 0:
        message = f"The experiment improves profit by {euro(profit_change)} and stays above the chosen cash floor."
        tone = "info"
    else:
        message = "The experiment does not improve profit. Try changing utilization, price or payment speed to see which lever matters."
        tone = "warning"

    raw = {
        "hires": hires,
        "utilization_change_pp": utilization,
        "billing_rate_change_pct": rate,
        "payment_delay_days": dso,
        "revenue_change_eur": revenue_change,
        "profit_change_eur": profit_change,
        "minimum_cash_eur": minimum_cash,
        "minimum_cash_change_eur": minimum_change,
        "ending_headcount": people,
    }
    return figure, kpis, callout("Result", message, tone), raw
