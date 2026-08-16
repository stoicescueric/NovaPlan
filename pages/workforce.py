"""Workforce economics and compensation-planning support."""

from __future__ import annotations

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from components.cards import callout, metric_card, status_pill
from components.charts import COLORS, style_figure
from components.controls import dropdown, number_input
from components.data_access import load_dataset
from components.formatting import euro, number, percent
from components.learning import chart_guide, learning_guide, teaching_callout
from components.page_utils import first_column, first_date_column
from components.tables import data_table
from models.workforce import evaluate_hire, simulate_hiring_plan


dash.register_page(
    __name__,
    path="/workforce",
    name="Workforce Planning",
    title="NovaPlan | Workforce Planning",
)


LEVELS = ["Junior", "Mid", "Senior", "Manager / Leadership", "Non-billable support"]
ROLE_OPTIONS = ["Consultant", "Software Engineer", "Data Engineer", "Solution Architect", "Project Manager"]
LEVEL_DEFAULTS = {
    "Junior": (27_000, 52, .72),
    "Mid": (42_000, 72, .76),
    "Senior": (60_000, 91, .74),
    "Manager / Leadership": (82_000, 112, .66),
    "Non-billable support": (34_000, 0, 0),
}


def _workforce_mix_figure(employees: pd.DataFrame) -> go.Figure:
    summary = (
        employees.groupby("seniority", as_index=False)
        .agg(fte=("employee_id", "count"), salary=("annual_base_salary_eur", "median"))
        .sort_values("fte")
    )
    figure = go.Figure(
        go.Bar(
            x=summary["fte"],
            y=summary["seniority"],
            orientation="h",
            marker_color=[COLORS["blue"], COLORS["accent_soft"], COLORS["accent"], COLORS["green"], COLORS["purple"]][: len(summary)],
            customdata=summary["salary"],
            hovertemplate="%{y}<br>%{x:.0f} FTE<br>Median salary €%{customdata:,.0f}<extra></extra>",
        )
    )
    figure.update_xaxes(ticksuffix=" FTE")
    return style_figure(figure, height=300, hovermode="closest")


def _salary_rows(employees: pd.DataFrame) -> list[dict]:
    grouped = employees.groupby("seniority")["annual_base_salary_eur"]
    rows = []
    for level in LEVELS:
        if level not in grouped.groups:
            continue
        values = grouped.get_group(level)
        rows.append(
            {
                "level": level,
                "fte": f"{len(values):,}",
                "p25": euro(values.quantile(.25), 0),
                "median": euro(values.median(), 0),
                "p75": euro(values.quantile(.75), 0),
            }
        )
    return rows


def layout() -> html.Div:
    employees = load_dataset("employees")
    history = load_dataset("monthly_kpis")
    last = history.iloc[-1]
    active = employees[employees.get("status", "Active").astype(str).eq("Active")] if "status" in employees else employees
    headcount = len(active)
    billable_mix = active["billable"].astype(bool).mean() if "billable" in active else float(last.get("billable_share", 0))
    revenue_per_fte = float(last.get("revenue_eur", 0)) * 12 / max(float(last.get("headcount", headcount)), 1)
    cost_per_fte = float(last.get("payroll_eur", 0)) * 12 / max(float(last.get("headcount", headcount)), 1)

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("People economics", className="page-kicker"),
                            html.H1("Grow capacity without losing economic discipline"),
                            html.P("Understand the existing workforce, test one hire, then see how a cohort changes profit and cash through ramp-up."),
                        ]
                    ),
                    status_pill("Compensation planning support", "positive"),
                ],
                className="page-heading",
            ),
            learning_guide(
                "Use this page to answer a practical question: will extra people create enough client revenue to cover their full cost without putting too much pressure on cash?",
                [
                    (
                        "Understand today's team",
                        "Start with active headcount, the billable mix, and the annualized revenue and payroll per employee. These describe the current workforce before any new hire is added.",
                    ),
                    (
                        "Describe one proposed hire",
                        "Choose the role and level, then review salary, utilization, billing rate, start date, and ramp-up. Every field is an assumption you can change.",
                    ),
                    (
                        "Check whether the economics work",
                        "Compare planned utilization with break-even utilization. Positive contribution is useful, but the cash chart also shows whether recruiting, equipment, and ramp-up create an early funding need.",
                    ),
                    (
                        "Test the whole hiring plan",
                        "A cohort can be profitable over 18 months and still consume cash at first. Use the amber cash line to judge whether the business can safely fund that low point.",
                    ),
                ],
                concepts=["FTE", "Billable mix", "Utilization", "Contribution", "Break-even", "Payback"],
                open_by_default=True,
            ),
            html.Div(
                [
                    metric_card(
                        "Active workforce",
                        number(headcount),
                        "Bucharest + Cluj-Napoca",
                        explanation="The number of employees currently marked active. One full-time employee counts as one FTE, or full-time equivalent.",
                        formula="Count of employee records where status = Active",
                    ),
                    metric_card(
                        "Billable mix",
                        percent(billable_mix),
                        f"{number(active['billable'].sum() if 'billable' in active else 0)} billable FTE",
                        explanation="The share of active employees whose time can be charged to clients. A higher share usually adds delivery capacity, but support roles are still necessary to run the company.",
                        formula="Billable active FTE / Total active FTE x 100",
                    ),
                    metric_card(
                        "Revenue / FTE",
                        euro(revenue_per_fte),
                        "annualized run-rate",
                        explanation="The latest month's revenue converted to a 12-month pace and divided by headcount. It is a quick productivity indicator, not a completed-year average.",
                        formula="Latest monthly revenue x 12 / Latest headcount",
                    ),
                    metric_card(
                        "Payroll / FTE",
                        euro(cost_per_fte),
                        "annualized employer cost",
                        explanation="The latest month's total payroll converted to a 12-month pace and divided by headcount. It helps compare people cost with revenue productivity.",
                        formula="Latest monthly payroll x 12 / Latest headcount",
                    ),
                ],
                className="metric-grid four",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Workforce by seniority"), html.P("Where is delivery capacity concentrated?")], className="panel-header"),
                            chart_guide("Bar length is the number of active employees at each level. Hover a bar to see its median base salary; a large concentration in one level may create delivery or succession risk."),
                            dcc.Graph(figure=_workforce_mix_figure(active), config={"displayModeBar": False}),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.Div([html.H3("Internal compensation bands"), html.P("Synthetic peer distribution; not a salary determination")], className="panel-header"),
                            data_table(
                                "workforce-salary-table",
                                _salary_rows(active),
                                columns=[
                                    {"name": "Level", "id": "level"},
                                    {"name": "FTE", "id": "fte"},
                                    {"name": "P25", "id": "p25"},
                                    {"name": "Median", "id": "median"},
                                    {"name": "P75", "id": "p75"},
                                ],
                                page_size=6,
                            ),
                            html.Div(
                                "P25 is the salary below which 25% of employees in that level fall; the median is the middle salary; P75 is the point below which 75% fall. These ranges describe this synthetic internal workforce, not the external job market.",
                                className="model-note",
                                style={"marginTop": "12px"},
                            ),
                        ],
                        className="panel",
                    ),
                ],
                className="content-grid equal",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3("Proposed hire", className="controls-title"),
                            html.P("Illustrative role economics over the first 12 months.", className="controls-description"),
                            html.Div(
                                [
                                    dropdown(
                                        "hire-role",
                                        "Role",
                                        ROLE_OPTIONS,
                                        "Consultant",
                                        hint="The job family being considered. The financial calculation is driven mainly by the level, pay, billing, and utilization assumptions below.",
                                    ),
                                    dropdown(
                                        "hire-level",
                                        "Level",
                                        LEVELS,
                                        "Mid",
                                        hint="Seniority sets sensible starting values for salary, billing rate, and utilization; you can still change each value.",
                                    ),
                                    number_input(
                                        "hire-salary",
                                        "Annual base salary",
                                        42_000,
                                        minimum=15_000,
                                        maximum=160_000,
                                        step=1_000,
                                        suffix="EUR",
                                        hint="Gross base salary for one full year, before employer on-cost, bonus, benefits, recruiting, and equipment.",
                                    ),
                                    number_input(
                                        "hire-utilization",
                                        "Expected utilization",
                                        76,
                                        minimum=0,
                                        maximum=95,
                                        step=1,
                                        suffix="%",
                                        hint="The share of available working time expected to be billed to clients. Training, leave, sales support, and idle time are not billed.",
                                    ),
                                    number_input(
                                        "hire-rate",
                                        "Billing rate",
                                        72,
                                        minimum=0,
                                        maximum=200,
                                        step=1,
                                        suffix="€/hr",
                                        hint="The client price for one billed hour before the realization adjustment for discounts or write-offs.",
                                    ),
                                    dropdown(
                                        "hire-start",
                                        "Start month",
                                        [{"label": pd.Timestamp(f"2026-{month:02d}-01").strftime("%b %Y"), "value": f"2026-{month:02d}-01"} for month in range(1, 10)],
                                        "2026-03-01",
                                        hint="The first month in which payroll, onboarding costs, and the productivity ramp begin.",
                                    ),
                                    number_input(
                                        "hire-ramp",
                                        "Productivity ramp",
                                        3,
                                        minimum=0,
                                        maximum=9,
                                        step=1,
                                        suffix="months",
                                        hint="How long the hire takes to reach planned productivity. Zero means full productivity from the first month.",
                                    ),
                                ],
                                className="controls-grid one",
                            ),
                            html.Div("Employer on-cost, bonus, benefits, recruiting, and equipment are separate illustrative assumptions.", className="model-note", style={"marginTop": "15px"}),
                        ],
                        className="controls-panel",
                    ),
                    html.Div(
                        [
                            html.Div(id="hire-economics-kpis", className="metric-grid four"),
                            html.Div(
                                [
                                    teaching_callout(
                                        "Contribution",
                                        "Contribution is the hire's expected first-year revenue left after recurring employer cost. Positive contribution means the revenue covers recurring people cost, but it does not by itself prove that every one-off cash cost has been recovered.",
                                        formula="Expected year-1 revenue - annual employer cost",
                                        example="If revenue is €100,000 and recurring employer cost is €60,000, contribution is €40,000.",
                                    ),
                                    teaching_callout(
                                        "Break-even utilization",
                                        "This is the minimum share of available hours that must be billed for steady-state revenue to cover recurring employer cost. Planned utilization above break-even provides a safety cushion.",
                                        formula="Annual employer cost / (billing rate x annual available hours x realization rate)",
                                        example="A 50% break-even level versus a 76% plan leaves a 26 percentage-point cushion.",
                                    ),
                                ],
                                className="content-grid equal",
                                style={"marginTop": "14px"},
                            ),
                            html.Div(id="hire-compensation-callout"),
                            html.Div(
                                [
                                    html.Div([html.H3("First-year economics"), html.P("When does the hire earn back the initial cash outlay?")], className="panel-header"),
                                    chart_guide("Revenue bars point upward and employer-cost bars point downward. The dark line adds each month's net cash effect; where it crosses zero, the hire has paid back the accumulated cash outlay."),
                                    dcc.Graph(id="hire-economics-chart", config={"displayModeBar": False}),
                                ],
                                className="panel",
                                style={"marginTop": "14px"},
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
                            html.Div([html.H3("Hiring cohort plan"), html.P("How does ramp-up separate profit creation from cash timing?")], className="panel-header"),
                            dcc.RadioItems(
                                id="hiring-plan-size",
                                options=[{"label": f"+{value} hires", "value": value} for value in [10, 25, 40, 50]],
                                value=40,
                                className="segmented-control",
                                inline=True,
                            ),
                            html.Div(
                                "Choose a cohort size to compare the same staggered hiring and ramp assumptions at a different scale.",
                                className="model-note",
                                style={"marginTop": "10px"},
                            ),
                            chart_guide("All three lines are cumulative. Revenue shows sales added, EBITDA subtracts payroll and recruiting, and cash also subtracts equipment. The lowest amber point is the largest temporary funding need."),
                            dcc.Graph(id="hiring-plan-chart", config={"displayModeBar": False}),
                        ],
                        className="panel",
                    ),
                    html.Div(id="hiring-plan-conclusion"),
                ],
                className="content-grid",
            ),
            html.Div(
                "Compensation ranges are generated from synthetic internal data and placeholder market logic. They are illustrative analytical ranges, not legal, tax, HR, or market advice.",
                className="disclaimer",
            ),
        ]
    )


@callback(
    Output("hire-salary", "value"),
    Output("hire-rate", "value"),
    Output("hire-utilization", "value"),
    Input("hire-level", "value"),
)
def set_level_defaults(level: str):
    salary, rate, utilization = LEVEL_DEFAULTS.get(level, LEVEL_DEFAULTS["Mid"])
    return salary, rate, utilization * 100


@callback(
    Output("hire-economics-kpis", "children"),
    Output("hire-compensation-callout", "children"),
    Output("hire-economics-chart", "figure"),
    Input("hire-role", "value"),
    Input("hire-level", "value"),
    Input("hire-salary", "value"),
    Input("hire-utilization", "value"),
    Input("hire-rate", "value"),
    Input("hire-start", "value"),
    Input("hire-ramp", "value"),
)
def update_hire_economics(
    role: str,
    level: str,
    salary: float,
    utilization: float,
    rate: float,
    start_month: str,
    ramp: int,
):
    employees = load_dataset("employees")
    result = evaluate_hire(
        role=role,
        seniority=level,
        base_salary_eur=float(salary or 0),
        joining_month=start_month,
        billing_rate_eur=float(rate or 0),
        utilization=float(utilization or 0) / 100,
        ramp_up_months=int(ramp or 0),
        internal_salary_data=employees,
    )
    annual_cost = float(result["total_annual_employer_cost_eur"])
    revenue = float(result["expected_billable_revenue_eur"])
    contribution = float(result["expected_contribution_margin_eur"])
    break_even = float(result["break_even_utilization"])
    cash_effect = float(result["cash_effect_12m_eur"])
    payback = result.get("expected_payback_period_months")
    kpis = [
        metric_card(
            "Annual employer cost",
            euro(annual_cost),
            "salary + on-cost + bonus + benefits",
            explanation="The recurring annual cost of employing this person. Recruiting and equipment are one-off cash costs and are therefore shown separately in the cash calculation.",
            formula="Base salary x (1 + employer on-cost rate + bonus rate) + annual benefits",
        ),
        metric_card(
            "Expected year-1 revenue",
            euro(revenue),
            f"{utilization or 0:.0f}% utilization",
            tone="positive",
            explanation="The client revenue expected during the first 12 months. It reflects billable hours, price, realization, and the slower productivity during ramp-up.",
            formula="Sum of monthly (available hours x billing rate x utilization x realization x ramp factor)",
        ),
        metric_card(
            "Contribution",
            euro(contribution),
            percent(result.get("contribution_margin_percent", 0)),
            tone="positive" if contribution > 0 else "negative",
            explanation="Expected first-year revenue remaining after recurring employer cost. A negative value means the hire does not cover recurring cost under the selected assumptions.",
            formula="Expected year-1 revenue - annual employer cost",
        ),
        metric_card(
            "Break-even utilization",
            percent(break_even),
            f"Payback {payback or '>36'} months",
            tone="positive" if break_even <= (utilization or 0) / 100 else "negative",
            explanation="The steady-state utilization needed for annual revenue to equal recurring employer cost. The footer also shows when cumulative cash turns non-negative; >36 means it does not happen within 36 months.",
            formula="Annual employer cost / (billing rate x annual available hours x realization rate)",
        ),
    ]
    compensation = callout(
        str(result.get("salary_position", "Analytical range")),
        (
            f"Internal P25–P75: {euro(result.get('internal_salary_low_eur', 0), 0)}–{euro(result.get('internal_salary_high_eur', 0), 0)}. "
            f"Recommended analytical range: {euro(result.get('recommended_analytical_low_eur', 0), 0)}–{euro(result.get('recommended_analytical_high_eur', 0), 0)}. "
            f"{result.get('internal_equity_flag', '')}."
        ),
        "warning" if "risk" in str(result.get("internal_equity_flag", "")).lower() else "info",
    )

    ramp_factors = result.get("ramp_factors", [1] * 12)
    months = pd.date_range(start_month, periods=12, freq="MS")
    monthly_revenue = [revenue * factor / max(sum(ramp_factors), 1) for factor in ramp_factors]
    monthly_cost = [annual_cost / 12] * 12
    cumulative_cash = pd.Series(monthly_revenue).sub(monthly_cost).cumsum()
    cumulative_cash.iloc[0] -= float(result.get("year_1_cash_cost_eur", annual_cost) - annual_cost)
    figure = go.Figure()
    figure.add_trace(go.Bar(x=months, y=monthly_revenue, name="Billable revenue", marker_color=COLORS["accent"]))
    figure.add_trace(go.Bar(x=months, y=[-value for value in monthly_cost], name="Employer cost", marker_color=COLORS["red"]))
    figure.add_trace(go.Scatter(x=months, y=cumulative_cash, name="Cumulative cash effect", line=dict(color=COLORS["ink"], width=2.5), yaxis="y2"))
    figure.update_layout(barmode="relative", yaxis2=dict(overlaying="y", side="right", showgrid=False, tickformat="€,.0s"))
    figure.update_yaxes(tickformat="€,.0s")
    style_figure(figure, height=330)
    return kpis, compensation, figure


@callback(
    Output("hiring-plan-chart", "figure"),
    Output("hiring-plan-conclusion", "children"),
    Input("hiring-plan-size", "value"),
)
def update_hiring_plan(hires: int):
    history = load_dataset("monthly_kpis")
    plan = simulate_hiring_plan(history, hires=int(hires or 40), months=18)
    dates = first_date_column(plan, ["month"])
    cumulative_revenue = first_column(plan, ["incremental_revenue_eur"]).cumsum()
    cumulative_ebitda = first_column(plan, ["incremental_ebitda_eur"]).cumsum()
    cumulative_cash = first_column(plan, ["cumulative_cash_effect_eur", "incremental_cash_effect_eur"])
    if "cumulative_cash_effect_eur" not in plan:
        cumulative_cash = cumulative_cash.cumsum()
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=dates, y=cumulative_revenue, name="Cumulative revenue", line=dict(color=COLORS["accent"], width=2.5)))
    figure.add_trace(go.Scatter(x=dates, y=cumulative_ebitda, name="Cumulative EBITDA", line=dict(color=COLORS["green"], width=2.3)))
    figure.add_trace(go.Scatter(x=dates, y=cumulative_cash, name="Cumulative cash effect", line=dict(color=COLORS["amber"], width=2.3, dash="dash")))
    figure.add_hline(y=0, line_color="#A9B3B1", line_width=1)
    figure.update_yaxes(tickformat="€,.0s")
    style_figure(figure, height=350)
    minimum_cash_effect = float(cumulative_cash.min())
    final_ebitda = float(cumulative_ebitda.iloc[-1])
    conclusion = callout(
        f"+{int(hires or 40)}-hire plan",
        f"The cohort adds {euro(final_ebitda)} of cumulative EBITDA over 18 months, while the early ramp produces a lowest cumulative cash effect of {euro(minimum_cash_effect)}. Staggering joins reduces that low point.",
        "warning" if minimum_cash_effect < 0 else "info",
    )
    return figure, conclusion
