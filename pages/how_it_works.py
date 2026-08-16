"""Plain-language research notes and methodology for the student project."""

from __future__ import annotations

import dash
from dash import dcc, html

from components.cards import callout
from components.data_access import load_dataset


dash.register_page(__name__, path="/how-it-works", name="How It Works", title="NovaPlan | How It Works")


def _formula(title: str, formula: str, meaning: str) -> html.Div:
    return html.Div(
        [html.H3(title), html.Code(formula), html.P(meaning)],
        className="panel soft",
    )


def layout() -> html.Div:
    datasets = {
        "Monthly business records": load_dataset("monthly_kpis"),
        "Invoices": load_dataset("invoices"),
        "Customers": load_dataset("customers"),
        "Employees": load_dataset("employees"),
        "Hiring plan": load_dataset("hiring_plan"),
        "Operating costs": load_dataset("opex"),
        "Capital purchases": load_dataset("capex"),
        "Weekly cash records": load_dataset("weekly_cash_actuals"),
    }

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Research notes", className="page-kicker"),
                            html.H1("How the project works"),
                            html.P("The model is intentionally simplified so every output can be traced to a small number of inputs."),
                        ]
                    )
                ],
                className="page-heading",
            ),
            callout(
                "Important",
                "Everything describes one fictional consulting company. The records are generated for learning and do not contain Deloitte or client data.",
                "warning",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H2("1. Synthetic data"),
                            html.P(
                                "Synthetic data means invented data that follows designed rules. Here, invoices add up to revenue, unpaid invoices become accounts receivable, and opening cash plus cash movement equals closing cash. Seed 42 makes the same fictional history repeatable."
                            ),
                            html.Table(
                                [
                                    html.Thead(html.Tr([html.Th("Dataset"), html.Th("Records"), html.Th("Used for")])),
                                    html.Tbody(
                                        [
                                            html.Tr([html.Td(name), html.Td(f"{len(frame):,}"), html.Td(
                                                "business and cash calculations" if name == "Monthly business records" else "supporting detail"
                                            )])
                                            for name, frame in datasets.items()
                                        ]
                                    ),
                                ],
                                className="simple-table",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("2. The main formulas"),
                            html.Div(
                                [
                                    _formula(
                                        "Revenue",
                                        "employees × billable share × working time × utilization × hourly rate",
                                        "More productive time or a higher price normally increases revenue.",
                                    ),
                                    _formula(
                                        "Operating profit",
                                        "revenue − payroll − contractor cost − other operating cost",
                                        "This project uses EBITDA as a simple operating-profit measure.",
                                    ),
                                    _formula(
                                        "Closing cash",
                                        "opening cash + cash collected − cash paid",
                                        "Profit and cash differ because customers may pay after revenue is recorded.",
                                    ),
                                ],
                                className="content-grid three",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("3. Three different experiments"),
                            html.Div(
                                [
                                    html.Div([html.H3("What-if scenario"), html.P("Change a few business assumptions together and compare one new plan with the base plan.")], className="panel soft"),
                                    html.Div([html.H3("13-week cash check"), html.P("Move customer receipts and near-term payments week by week to find the tightest cash point.")], className="panel soft"),
                                    html.Div([html.H3("Monte Carlo"), html.P("Repeat the forecast many times with random driver changes to see a range instead of one answer.")], className="panel soft"),
                                ],
                                className="content-grid three",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("4. How Monte Carlo is tested"),
                            html.Ol(
                                [
                                    html.Li("With uncertainty set to 0%, every run must collapse to the same cash path."),
                                    html.Li("Higher uncertainty must create a wider P5-to-P95 range."),
                                    html.Li("Changing the cash safety target must change the breach percentage, not the simulated cash paths."),
                                    html.Li("The same seed and assumptions must reproduce the same result."),
                                ]
                            ),
                            html.P(
                                "The complete automated suite also checks revenue drivers, customer-payment timing, salaries, hiring ramp-up, cash roll-forwards and statement reconciliation."
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("Optional deeper pages"),
                            html.P("These pages remain available for someone who wants to inspect the original detailed prototype:"),
                            html.Div(
                                [
                                    dcc.Link("Full scenario lab", href="/scenario-lab", className="button secondary"),
                                    dcc.Link("Forecast diagnostics", href="/diagnostics", className="button secondary"),
                                    dcc.Link("Data assumptions", href="/data-assumptions", className="button secondary"),
                                ],
                                style={"display": "flex", "gap": "10px", "flexWrap": "wrap"},
                            ),
                        ],
                        className="panel soft",
                    ),
                ]
            ),
            html.P(
                "NovaPlan is an educational proof-of-concept built using entirely synthetic data. It is not an official Deloitte product and is not financial, tax, accounting or investment advice.",
                className="page-disclaimer",
            ),
        ]
    )
