"""Plain-language research notes and methodology for the student project."""

from __future__ import annotations

from pathlib import Path

import dash
import pandas as pd
import yaml
from dash import html

from components.data_access import load_dataset
from components.formatting import euro, number, percent
from models.forecast import DEFAULT_FORECAST_OPTIONS
from models.monte_carlo import DEFAULT_MONTE_CARLO_OPTIONS


dash.register_page(__name__, path="/how-it-works", name="How It Works", title="NovaPlan | How It Works")


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_generation_assumptions() -> dict:
    """Read the rules used to create the fictional 2020–2025 history."""
    with (PROJECT_ROOT / "config" / "assumptions.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _explain_row(label: str, value: str, meaning: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                [html.Strong(label), html.Span(value, className="explain-value")],
                className="explain-term",
            ),
            html.P(meaning),
        ],
        className="explain-row",
    )


def _formula(title: str, formula: str, meaning: str) -> html.Div:
    return html.Div(
        [html.H3(title), html.Code(formula), html.P(meaning)],
        className="formula-row",
    )


def _details(title: str, children) -> html.Details:
    return html.Details(
        [html.Summary(title), html.Div(children, className="plain-details-body")],
        className="plain-details",
    )


def layout() -> html.Div:
    generation = _load_generation_assumptions()
    history = load_dataset("monthly_kpis").sort_values("month")
    invoices = load_dataset("invoices")
    customers = load_dataset("customers")
    employees = load_dataset("employees")
    hiring_plan = load_dataset("hiring_plan")
    opex = load_dataset("opex")
    capex = load_dataset("capex")
    weekly_cash = load_dataset("weekly_cash_actuals")

    datasets = {
        "Monthly business records": (history, "Revenue, profit, working capital and cash by month"),
        "Invoices": (invoices, "Invoice dates, amounts and customer payment dates"),
        "Customers": (customers, "Customer size, mix and concentration"),
        "Employees": (employees, "Role, pay, billable status and hire date"),
        "Hiring plan": (hiring_plan, "The fictional 40-person plan and its start dates"),
        "Operating costs": (opex, "Eleven cost categories by month"),
        "Capital purchases": (capex, "Equipment purchases and depreciation lives"),
        "Weekly cash records": (weekly_cash, "Past weekly receipts and payments"),
    }

    latest = history.iloc[-1]
    recent_six = history.tail(6)
    latest_month = pd.Timestamp(latest["month"])
    forecast_months = 18
    forecast_end = latest_month + pd.DateOffset(months=forecast_months)
    base_utilization = float(history.tail(12)["utilization"].mean())
    base_realization = float(history.tail(12)["realization_rate"].mean())
    base_dso = float(recent_six["dso"].mean())
    base_dpo = float(recent_six["dpo"].mean())
    payroll_per_person = float((recent_six["payroll_eur"] / recent_six["headcount"]).mean())
    baseline_hires = float(recent_six["new_hires"].mean())
    prior_year_income = float(history.loc[history["month"].dt.year == 2025, "net_income_eur"].sum())
    omitted_distribution = prior_year_income * float(generation["cash"]["distribution_share_of_prior_year_net_income"])
    weekly_factor = 12 / 52
    weekly_baselines = {
        "Customer collections": float(history.tail(3)["cash_collections_eur"].mean() * weekly_factor),
        "Payroll": float(history.tail(3)["payroll_eur"].mean() * weekly_factor),
        "Supplier payments": float(history.tail(3)["vendor_payments_eur"].mean() * weekly_factor),
        "Tax payments": float(history.tail(3)["tax_payments_eur"].mean() * weekly_factor),
        "Equipment and other capex": float(history.tail(3)["capex_eur"].mean() * weekly_factor),
    }

    tax_rate = float(DEFAULT_FORECAST_OPTIONS["tax_rate"])
    uncertainty = DEFAULT_MONTE_CARLO_OPTIONS

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H1("How the project works, without hiding the rules"),
                            html.P(
                                "This page is the missing instruction sheet: what the invented company looks like, what each calculation assumes, and what the dashboard leaves out."
                            ),
                        ]
                    )
                ],
                className="page-heading",
            ),
            html.P(
                "NovaPlan is a student project about one fictional Romanian IT consulting company. No Deloitte, client or real employee data is used.",
                className="research-note",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H2("1. From an invented company to a decision"),
                            html.P(
                                "The project first makes a pretend business history. It then uses a few simple financial rules to ask practical questions such as ‘Can we afford 40 more people?’"
                            ),
                            html.Ol(
                                [
                                    html.Li("Choose the business rules"),
                                    html.Li("Create employees and customers"),
                                    html.Li("Turn work into invoices"),
                                    html.Li("Turn invoices and costs into cash"),
                                    html.Li("Move a slider and compare the result"),
                                ],
                                className="project-flow",
                            ),
                            html.H3("What does ‘synthetic data’ mean?", className="panel-subheading"),
                            html.Div(
                                [
                                    _explain_row("Invented", "not collected", "The names, employees, customers and transactions were created for this project."),
                                    _explain_row("Linked", "one story", "Invoices add up to revenue. When customers pay, unpaid invoices and cash move too."),
                                    _explain_row("Realistic-looking", "not real evidence", "Busy months, quieter summers, staff departures and late payments make the history feel believable, but they do not describe a real company."),
                                    _explain_row("Repeatable", "seed 42", "Seed 42 is like a bookmark. Running the generator again with the same seed recreates the same pretend history."),
                                ],
                                className="explain-list",
                            ),
                            html.H3("How much invented data is there?", className="panel-subheading"),
                            html.Div(
                                [
                                    _explain_row("Monthly history", f"{len(history):,} months", "January 2020 through December 2025."),
                                    _explain_row("People", f"{int(latest['headcount']):,} active", f"{int(latest['billable_headcount']):,} can work directly on customer projects at December 2025."),
                                    _explain_row("Customers and invoices", f"{len(customers):,} and {len(invoices):,}", "The invoices connect earned revenue to later customer cash receipts."),
                                    _explain_row("Weekly cash history", f"{len(weekly_cash):,} weeks", "A separate short history of cash collected and cash paid."),
                                ],
                                className="explain-list compact",
                            ),
                            _details(
                                "See every generated file",
                                html.Div(
                                    html.Table(
                                        [
                                            html.Thead(html.Tr([html.Th("File in plain English"), html.Th("Rows"), html.Th("What it contains")])),
                                            html.Tbody(
                                                [
                                                    html.Tr([html.Td(name), html.Td(f"{len(frame):,}"), html.Td(use)])
                                                    for name, (frame, use) in datasets.items()
                                                ]
                                            ),
                                        ],
                                        className="simple-table",
                                    ),
                                    className="table-scroll",
                                ),
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("2. Where the experiments start"),
                            html.P(
                                "The forecast does not begin with an empty company. It picks up after the final invented month, December 2025."
                            ),
                            html.Div(
                                [
                                    _explain_row("Cash in the bank", euro(float(latest["closing_cash_eur"]), 2), "The money left at the end of the invented history. Every experiment starts from this balance."),
                                    _explain_row("Employees", number(float(latest["headcount"])), f"{int(latest['billable_headcount'])} are billable, meaning their time can be charged to a customer."),
                                    _explain_row("Utilization that month", percent(float(latest["utilization"])), "Out of 100 hours available from billable people, about 72 were sold to customers in December 2025."),
                                    _explain_row("Average client price", f"€{float(latest['billing_rate_eur']):,.2f} per hour", "This is one blended price across the pretend company, not a price for every person or project."),
                                    _explain_row("Customer payment time", f"{float(latest['dso']):.1f} days", "This is DSO: roughly how long earned invoice money waits before becoming cash."),
                                ],
                                className="explain-list",
                            ),
                            html.P(
                                [
                                    "The invented history itself began in January 2020 with ",
                                    html.Strong(f"{generation['workforce']['opening_headcount']} employees"),
                                    " and ",
                                    html.Strong(euro(float(generation["cash"]["opening_cash_eur"]), 2)),
                                    ". Those are history-start values; the experiments use the December 2025 values above.",
                                ],
                                className="context-note",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("3. The important assumptions behind the screen"),
                            html.P(
                                "A CSV can show the finished numbers, but it cannot explain every rule that made them. These are the choices the live dashboard uses."
                            ),
                            html.H3("Work and revenue", className="panel-subheading"),
                            html.Div(
                                [
                                    _explain_row("Forecast window", f"{forecast_months} months", f"January 2026 through {forecast_end.strftime('%B %Y')}. ‘End cash’ means June 2027 cash, not calendar year-end cash."),
                                    _explain_row("Working time", "8 hours per weekday", "The forecast counts Monday to Friday. It does not remove Romanian public holidays, so available hours are slightly simplified."),
                                    _explain_row("Starting utilization", percent(base_utilization), "This is the average of the final 12 invented months. About 75 of every 100 available billable hours were sold."),
                                    _explain_row("Billable share", percent(float(history.tail(12)["billable_share"].mean())), "About 87 of every 100 employees can directly create client revenue; the rest support the business."),
                                    _explain_row("Revenue realization", percent(base_realization), "If the theoretical work value is €100, the model records about €96.40 after discounts and other leakage."),
                                    _explain_row("Normal growth", "+5% demand; +3% price each year", "The base plan slowly grows both the amount of work wanted and the price per hour. These are classroom choices, not promises."),
                                ],
                                className="explain-list",
                            ),
                            html.H3("People and operating costs", className="panel-subheading"),
                            html.Div(
                                [
                                    _explain_row("Hiring already in the base plan", f"about {baseline_hires:.1f} people each month", "Extra hires from the slider are added on top of this recent hiring pace. Staff departures also continue."),
                                    _explain_row("When extra hires arrive", "spread over 6 months", "A 40-person choice becomes 7, 7, 7, 7, 6 and 6 arrivals, rather than all 40 on day one."),
                                    _explain_row("New-hire ramp", "⅓, ⅔, then full capacity", "The forecast pays the full employee cost from the joining month, but lets client-work capacity build over 3 months."),
                                    _explain_row("One new hire", "€3,000 recruiting + €1,800 equipment", "Recruiting lowers operating profit and cash. Equipment is treated as a long-life purchase, so cash falls now but EBITDA does not."),
                                    _explain_row("Forecast payroll", f"about {euro(payroll_per_person)} per employee per month", "The model starts from the latest six-month average total payroll cost and grows it by 6% per year."),
                                    _explain_row("Other operating costs", "+3.5% per year", "Rent, software and similar costs are split into a mostly fixed part and a smaller part that moves with revenue."),
                                ],
                                className="explain-list",
                            ),
                            _details(
                                "What was inside historical payroll?",
                                [
                                    html.P(
                                        "For the invented 2020–2025 history, payroll included base salary, a role-based bonus, a 2.25% employer on-cost (an extra company cost on top of salary) and €205 of monthly benefits per employee. The starting bonus rates were 3% for Junior, 5% for Mid, 8% for Senior, 12% for Manager and 5% for support roles. Salary reviews happened each April."
                                    ),
                                    html.P(
                                        "The live forecast does not rebuild those pieces one by one. They are already mixed into the recent payroll average above, which is then increased by 6% per year. These figures are fictional and are not Romanian payroll or employment guidance."
                                    ),
                                ],
                            ),
                            _details(
                                "How equipment becomes an expense over time",
                                [
                                    html.P(
                                        f"The invented history spread laptop cost over {generation['capex']['laptop_useful_life_months']} months, office improvements over {generation['capex']['office_improvement_useful_life_months']} months and strategic technology over {generation['capex']['strategic_technology_useful_life_months']} months. This spreading is called depreciation: the cash is paid when the asset is bought, but the accounting expense is shared across the years it is used."
                                    ),
                                    html.P(
                                        "The live forecast is simpler. It starts with the latest monthly depreciation and adds one thirty-sixth of new capital purchases. It does not keep a complete future asset register."
                                    ),
                                ],
                            ),
                            html.H3("Cash, suppliers and tax", className="panel-subheading"),
                            html.Div(
                                [
                                    _explain_row("Customer payment time", f"about {base_dso:.1f} days", "Revenue is earned first. Cash arrives later, so a longer wait creates more unpaid customer invoices and less cash."),
                                    _explain_row("Supplier payment time", f"about {base_dpo:.1f} days", "Costs are recorded first. Waiting longer to pay a supplier temporarily keeps more cash in the bank."),
                                    _explain_row("Example operating cash floor", euro(float(DEFAULT_FORECAST_OPTIONS["minimum_cash_threshold_eur"])), "This is a chosen classroom warning line, not a legal, bank or Deloitte rule."),
                                    _explain_row("Illustrative corporate tax", percent(tax_rate, 0), "The monthly forecast uses 16% of positive EBITDA after depreciation and assumes that tax cash leaves in the same month."),
                                ],
                                className="explain-list",
                            ),
                            _details(
                                "How tax differs between the invented history and the forecast",
                                [
                                    html.P(
                                        "In the invented history, tax expense was 16% of positive operating profit after depreciation and interest, and the tax bill was paid quarterly in March, June, September and December. In the live 18-month forecast, tax is simplified to 16% of positive EBITDA after depreciation and is paid immediately each month."
                                    ),
                                    html.P(
                                        "The model does not calculate VAT, personal tax, payroll tax, deferred tax, tax losses carried into another year or country-specific tax rules. The 16% is only a teaching assumption, not tax advice."
                                    ),
                                ],
                            ),
                            _details(
                                "What the 13-week cash check fills in when no invoice date is known",
                                [
                                    html.P(
                                        "Known invoice dates are used where possible. For an empty future week, the model falls back to a recent weekly average:"
                                    ),
                                    html.Ul(
                                        [html.Li(f"{name}: about {euro(value)} per week") for name, value in weekly_baselines.items()],
                                        className="method-list",
                                    ),
                                    html.P(
                                        "The weekly tax amount is a recent cash-payment average, not a fresh 16% tax calculation. Extra hires add costs but no new revenue during this short view."
                                    ),
                                ],
                            ),
                            html.Div(
                                [
                                    html.Strong("One important cash omission"),
                                    html.P(
                                        [
                                            "The invented history paid 60% of the prior year’s positive net income to its owners each May. Applying that old rule in May 2026 would mean about ",
                                            html.Strong(euro(omitted_distribution)),
                                            ", but the forward forecast does not include it. It also leaves out interest, new debt, dividends, VAT and emergency funding. This is one reason forecast cash can look unusually comfortable.",
                                        ]
                                    ),
                                ],
                                className="assumption-warning",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("4. What a slider changes—and what it leaves alone"),
                            html.Div(
                                [
                                    _explain_row("Extra employees", "cost first, capacity later", "Payroll, recruiting and equipment begin as people join. Their ability to create revenue grows over the 3-month ramp."),
                                    _explain_row("Utilization", "sold hours", "It changes how many available hours become customer work. It does not change employee count or hourly price."),
                                    _explain_row("Billing rate", "price per sold hour", "It changes revenue on the same work. It does not create more people or more available hours."),
                                    _explain_row("Customer payment time", "cash timing only", "The invoice and profit stay the same; only the day the money reaches the bank moves."),
                                    _explain_row("Unexpected week-1 payment", "one cash subtraction", "It lowers week 1 and every balance after it once. It is not a new monthly cost."),
                                    _explain_row("Monte Carlo uncertainty", "width of the range", "It changes how far the random drivers can move, not the selected base plan."),
                                    _explain_row("Cash comparison target", "classification only", "Moving the line can change the ‘chance below target,’ but it cannot move any simulated cash path."),
                                ],
                                className="explain-list",
                            ),
                            html.H3("Three formulas are enough to follow the story", className="panel-subheading"),
                            html.Div(
                                [
                                    _formula(
                                        "Revenue",
                                        "people × billable share × workdays × 8h × utilization × hourly price × realization",
                                        "People create available time; utilization sells part of it; the billing rate puts a price on it.",
                                    ),
                                    _formula(
                                        "Operating profit (EBITDA)",
                                        "revenue − payroll − contractors − other operating costs",
                                        "EBITDA is a simple view of profit from normal operations before depreciation, interest and tax.",
                                    ),
                                    _formula(
                                        "Closing cash",
                                        "opening cash + cash collected − cash paid",
                                        "Profit and cash differ because an invoice can count as revenue weeks before the customer pays it.",
                                    ),
                                ],
                                className="formula-list",
                            ),
                            html.H3("How to read the main outputs", className="panel-subheading"),
                            html.Div(
                                [
                                    _explain_row("Revenue", "work earned", "The value of customer work in the period, even if the customer has not paid yet."),
                                    _explain_row("EBITDA", "operating profit", "Revenue left after payroll, contractors and normal operating costs. It is not the same as net income or cash."),
                                    _explain_row("Lowest cash", "tightest point", "The smallest closing balance anywhere in the chosen forecast, not just the final month."),
                                    _explain_row("P5 / middle / P95", "low / typical / high", "P5 is a low end result, the middle has half the runs on each side, and P95 is a high end result. They describe the final month."),
                                    _explain_row("Chance below target", "paths crossing the line", "The share of simulated paths that fall below the chosen comparison target at least once in any month."),
                                ],
                                className="explain-list compact",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("5. Monte Carlo: the same plan, many possible tomorrows"),
                            html.P(
                                "A normal forecast pretends every input will be exactly right. Monte Carlo repeats the 18-month plan while business drivers wobble. It never picks a random cash number: a driver first changes revenue, costs or collections, and those changes create a new cash path."
                            ),
                            html.Div(
                                [
                                    _explain_row("0% uncertainty", "no wobble", "Every run follows the same no-surprise forecast, so the shaded range collapses into one line."),
                                    _explain_row("100% uncertainty", "built-in wobble", "The model uses the driver ranges listed below."),
                                    _explain_row("200% uncertainty", "twice the range", "The random movements double, but hard limits stop impossible values."),
                                    _explain_row("2,000 / 5,000 / 10,000 runs", "more repetitions", "More runs make percentages steadier. They do not create more business risk."),
                                    _explain_row("Seed 42", "same random sequence", "The same inputs and seed reproduce the same simulation so the experiment can be checked."),
                                ],
                                className="explain-list compact",
                            ),
                            html.H3("At 100%, what is allowed to wobble?", className="panel-subheading"),
                            html.Div(
                                [
                                    _explain_row("Utilization", f"{float(uncertainty['utilization_monthly_std_pp']) * 100:.1f} percentage points each month", "How much available client time gets sold."),
                                    _explain_row("Customer payment time", f"{float(uncertainty['dso_monthly_std_days']):.0f} days each month", "How quickly invoices turn into cash."),
                                    _explain_row("Billing realization", f"{float(uncertainty['billing_realization_std_pct']) * 100:.1f}% each month", "How much of the theoretical client-work value becomes revenue."),
                                    _explain_row("Backlog conversion", f"{float(uncertainty['backlog_conversion_std_pct']) * 100:.0f}% each month", "How much planned work becomes real revenue."),
                                    _explain_row("Salary inflation", f"{float(uncertainty['annual_salary_inflation_std_pp']) * 100:.1f} percentage points per run", "One salary-cost surprise affects the whole 18-month path."),
                                    _explain_row("Staff departures", f"{float(uncertainty['annual_attrition_std_pp']) * 100:.1f} percentage points per run", "One attrition surprise changes the number of people available through the path."),
                                    _explain_row("EUR/RON exchange rate", f"{float(uncertainty['fx_std_pct']) * 100:.1f}% per run", "A simple currency surprise changes euro payroll cost in the model."),
                                ],
                                className="explain-list",
                            ),
                            html.P(
                                "Good or bad conditions can last for several months: 70% of one month’s shared business mood carries into the next. This relationship was designed for the project; it was not learned from real market data.",
                                className="context-note",
                            ),
                            _details(
                                "See the guardrails that stop extreme random values",
                                html.Ul(
                                    [
                                        html.Li("Utilization stays between 55% and 90%."),
                                        html.Li("Customer payment time stays between 30 and 95 days."),
                                        html.Li("The billing factor stays between 90% and 108% of plan."),
                                        html.Li("Backlog conversion stays between 82% and 118% of plan."),
                                        html.Li("Salary and attrition surprises are clipped; the FX surprise stays between −5% and +5%."),
                                    ],
                                    className="method-list",
                                ),
                            ),
                            html.P(
                                "The simulation does not randomize tax rates, supplier payment time, equipment prices, debt, a single large customer loss, a recession, a cyber event or emergency funding. Its percentages describe this invented model—not the real-world probability of an event.",
                                className="context-note",
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.H2("6. How I checked it—and what it cannot prove"),
                            html.H3("Checks built into the project", className="panel-subheading"),
                            html.Ul(
                                [
                                    html.Li("Each month’s invoices add back to that month’s revenue."),
                                    html.Li("Opening cash plus the month’s movement equals closing cash."),
                                    html.Li("Opening staff plus hires minus departures equals closing staff."),
                                    html.Li("At 0% uncertainty, all Monte Carlo runs become one line; more uncertainty widens the range."),
                                    html.Li("Using seed 42 twice gives the same simulated result twice."),
                                ],
                                className="method-list",
                            ),
                            html.H3("Limits to remember", className="panel-subheading"),
                            html.Ul(
                                [
                                    html.Li("Synthetic patterns are designed examples, not evidence about a real company."),
                                    html.Li("The forecast uses one blended company average rather than forecasting every client, role and project."),
                                    html.Li("Tax, public holidays, depreciation, working capital and the 13-week timing rules are deliberately simplified."),
                                    html.Li("A few fictional invoices contain future payment dates. A real forecast would only know expected dates, not the future."),
                                    html.Li("A model can repeat perfectly and still be wrong if its assumptions are unrealistic."),
                                ],
                                className="method-list",
                            ),
                        ],
                        className="panel",
                    ),
                ],
                className="section-stack",
            ),
            html.P(
                "NovaPlan is an educational proof-of-concept built using entirely synthetic data. It is not an official Deloitte product and is not financial, tax, accounting or investment advice.",
                className="page-disclaimer",
            ),
        ],
        className="primary-page",
    )
