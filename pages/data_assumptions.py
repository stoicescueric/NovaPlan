"""Data lineage, model assumptions, governance, and limitations."""

from __future__ import annotations

from pathlib import Path

import dash
import pandas as pd
import yaml
from dash import Input, Output, callback, html

from components.audit import read_audit_log
from components.cards import metric_card, status_pill
from components.data_access import DATA_DIR, load_dataset
from components.formatting import number
from components.learning import learning_guide, teaching_callout
from components.tables import data_table


dash.register_page(
    __name__,
    path="/data-assumptions",
    name="Data & Assumptions",
    title="NovaPlan | Data & Assumptions",
)


ROOT = Path(__file__).resolve().parents[1]


ASSUMPTION_ROWS = [
    ("Minimum cash threshold", "3,000,000", "EUR", "Policy floor for liquidity monitoring", "Management Assumption"),
    ("Hours per working day", "8.0", "hours", "Available capacity per employee day", "Management Assumption"),
    ("Realization rate", "97.0", "%", "Share of billable value recognized as revenue", "Model Estimate"),
    ("Employer on-cost", "8.0", "%", "Illustrative financial assumption; not Romanian tax guidance", "Management Assumption"),
    ("Bonus assumption", "8.0", "% salary", "Illustrative annual variable compensation", "Management Assumption"),
    ("Hire productivity ramp", "3", "months", "Time for a new billable employee to reach planned productivity", "Management Assumption"),
    ("DSO", "Calculated", "days", "Accounts receivable divided by revenue run-rate", "Calculated"),
    ("Monthly revenue", "Driver tree", "EUR", "Capacity × utilization × rate × realization", "Calculated"),
    ("EUR/RON", "Historical path", "RON/EUR", "Slow-moving synthetic external assumption", "Observed"),
    ("Monte Carlo seed", "42", "integer", "Reproducibility control", "Management Assumption"),
]


DATASETS = [
    ("monthly_kpis", "Monthly operational drivers and linked financial outcomes", "Synthetic"),
    ("invoices", "Invoice-level terms, due dates, collections, and lateness", "Synthetic"),
    ("customers", "Customer profiles, concentration, and payment behavior", "Synthetic"),
    ("employees", "Active workforce, salary, billing rate, and utilization assumptions", "Synthetic"),
    ("hiring_plan", "2026 expansion cohorts and ramp assumptions", "Synthetic"),
    ("opex", "Monthly fixed and variable operating-cost detail", "Synthetic"),
    ("capex", "New-hire equipment and asset-light capital spending", "Synthetic"),
    ("weekly_cash_actuals", "Historical direct cash bridge", "Synthetic"),
]


def _assumption_records() -> list[dict]:
    return [
        {"name": name, "value": value, "unit": unit, "description": description, "type": assumption_type}
        for name, value, unit, description, assumption_type in ASSUMPTION_ROWS
    ]


def _dataset_records() -> list[dict]:
    records = []
    for name, description, source in DATASETS:
        frame = load_dataset(name)
        records.append(
            {
                "dataset": f"{name}.csv",
                "rows": f"{len(frame):,}",
                "columns": f"{len(frame.columns):,}",
                "description": description,
                "source": source,
            }
        )
    return records


def _audit_records() -> list[dict]:
    audit = read_audit_log().tail(50).iloc[::-1]
    if audit.empty:
        return [
            {
                "timestamp": "—",
                "scenario": "No changes yet",
                "variable": "—",
                "old_value": "—",
                "new_value": "—",
                "user": "Demo User",
                "rationale": "Save a scenario or management overlay to begin the audit trail.",
            }
        ]
    return audit.fillna("—").to_dict("records")


def layout() -> html.Div:
    monthly = load_dataset("monthly_kpis")
    invoices = load_dataset("invoices")
    employees = load_dataset("employees")
    customers = load_dataset("customers")
    start_month = pd.to_datetime(monthly["month"]).min()
    end_month = pd.to_datetime(monthly["month"]).max()

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Transparency & governance", className="page-kicker"),
                            html.H1("Know what is observed, assumed, calculated, or estimated"),
                            html.P("A concise inventory of synthetic data, model assumptions, audit history, and analytical limitations."),
                        ]
                    ),
                    status_pill("Model version 0.1.0", "positive"),
                ],
                className="page-heading",
            ),
            learning_guide(
                "Use this page to trace where every important number comes from and to separate facts from management choices and model outputs.",
                [
                    (
                        "Check the evidence base",
                        "The first cards show how much synthetic history sits behind the prototype. More rows can provide useful detail, but synthetic volume does not make the information real-world evidence.",
                    ),
                    (
                        "Read the provenance type",
                        "For each important input, identify whether it was observed, calculated, assumed by management, or estimated by a model. These labels tell you how much interpretation is involved.",
                    ),
                    (
                        "Trace the source",
                        "Use the data dictionary to see which generated file supports each part of the simulator. Dataset rows are raw records; dashboard metrics are often calculations made from those records.",
                    ),
                    (
                        "Review changes and limitations",
                        "The audit log records scenario edits without overwriting the baseline. Read the limitations before relying on a result, because a transparent model can still be simplified or uncertain.",
                    ),
                ],
                concepts=["Observed", "Calculated", "Management assumption", "Model estimate", "Data lineage", "Audit trail"],
                open_by_default=True,
            ),
            html.Div(
                [
                    metric_card(
                        "Historical coverage",
                        f"{start_month:%b %Y} – {end_month:%b %Y}",
                        f"{len(monthly)} months",
                        explanation="The earliest and latest months in the synthetic monthly KPI file. This is the time window available for trend analysis and forecast backtesting.",
                        formula="Earliest month = min(month); latest month = max(month); count = number of monthly rows",
                    ),
                    metric_card(
                        "Invoice records",
                        number(len(invoices)),
                        "customer-level payment behavior",
                        explanation="The number of synthetic invoice rows used to model due dates, collections, lateness, and customer payment patterns. One row represents one invoice, not one customer.",
                        formula="Count of rows in invoices.csv",
                    ),
                    metric_card(
                        "Employee records",
                        number(len(employees)),
                        "synthetic workforce snapshot",
                        explanation="The number of synthetic employee rows available for workforce mix, compensation ranges, billing assumptions, and utilization analysis. One row represents one employee record.",
                        formula="Count of rows in employees.csv",
                    ),
                    metric_card(
                        "Customer profiles",
                        number(len(customers)),
                        "Western European portfolio",
                        explanation="The number of fictional customer profiles used for concentration and payment-behavior analysis. A profile may be linked to many invoice records.",
                        formula="Count of rows in customers.csv",
                    ),
                ],
                className="metric-grid four",
            ),
            html.Div(
                [
                    teaching_callout(
                        "Observed",
                        "A value recorded directly in the source data for a past period. The model may clean or display it, but does not invent the underlying event.",
                        formula="Displayed observed value = recorded source field",
                        example="A historical synthetic EUR/RON rate stored for a particular month.",
                    ),
                    teaching_callout(
                        "Calculated",
                        "A value produced by a fixed, repeatable rule from other values. If the inputs are the same, the calculation should always give the same result.",
                        formula="Monthly revenue = capacity x utilization x billing rate x realization",
                        example="DSO is calculated from receivables and the revenue run-rate rather than typed in as a historical value.",
                    ),
                    teaching_callout(
                        "Management assumption",
                        "A deliberate planning choice or policy supplied by a decision-maker. It is neither a historical fact nor a prediction and should be challenged with scenarios.",
                        formula="Scenario result = model result using the selected assumption",
                        example="Management chooses a €3 million minimum cash threshold as the policy floor.",
                    ),
                    teaching_callout(
                        "Model estimate",
                        "A quantity inferred by a method when it is not directly observed. An estimate depends on data, assumptions, and methodology, so it carries uncertainty.",
                        formula="Estimate = method(observed data, assumptions)",
                        example="A 97% realization rate is estimated for planning from the model's synthetic operating pattern.",
                    ),
                ],
                className="content-grid equal",
                style={"marginBottom": "16px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Assumption register"), html.P("Every key input has a value, unit, description, and provenance type")], className="panel-header"),
                            data_table(
                                "assumptions-table",
                                _assumption_records(),
                                columns=[
                                    {"name": "Name", "id": "name"},
                                    {"name": "Value", "id": "value"},
                                    {"name": "Unit", "id": "unit"},
                                    {"name": "Description", "id": "description"},
                                    {"name": "Type", "id": "type"},
                                ],
                                page_size=12,
                            ),
                            html.Div(
                                "Read each row from left to right: the name says what the item is, value and unit show its size, description says how it is used, and Type tells you its provenance. Assumptions and estimates deserve sensitivity testing; calculated values deserve formula checks.",
                                className="model-note",
                                style={"marginTop": "12px"},
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.Div([html.H3("Model identity"), html.P("Scope and governance metadata")], className="panel-header"),
                            html.Div(
                                [
                                    html.Div([html.Div("Company", className="comparison-label"), html.Div("NovaBridge Digital SRL", className="comparison-value", style={"fontSize": "13px"})], className="comparison-item"),
                                    html.Div([html.Div("Data source", className="comparison-label"), html.Div("Synthetic", className="comparison-value")], className="comparison-item"),
                                    html.Div([html.Div("Seed", className="comparison-label"), html.Div("42", className="comparison-value")], className="comparison-item"),
                                    html.Div([html.Div("User", className="comparison-label"), html.Div("Demo User", className="comparison-value", style={"fontSize": "13px"})], className="comparison-item"),
                                ],
                                className="comparison-strip",
                                style={"gridTemplateColumns": "1fr"},
                            ),
                            html.Div(
                                "Financial relationships are explicit: revenue follows capacity and commercial drivers; collections follow invoices and payment behavior; capex affects cash but not EBITDA.",
                                className="model-note",
                                style={"marginTop": "14px"},
                            ),
                            html.Div(
                                "Model version identifies this specific set of logic. Seed 42 makes the synthetic data reproducible, so rebuilding with the same code and seed produces the same fictional records.",
                                className="model-note",
                                style={"marginTop": "10px"},
                            ),
                        ],
                        className="panel",
                    ),
                ],
                className="content-grid",
            ),
            html.Div(
                [
                    html.Div([html.H3("Data dictionary"), html.P("Generated files used by the MVP")], className="panel-header"),
                    data_table(
                        "datasets-table",
                        _dataset_records(),
                        columns=[
                            {"name": "Dataset", "id": "dataset"},
                            {"name": "Rows", "id": "rows"},
                            {"name": "Columns", "id": "columns"},
                            {"name": "Description", "id": "description"},
                            {"name": "Source", "id": "source"},
                        ],
                        page_size=10,
                    ),
                    html.Div(
                        "Rows are individual records and columns are the fields stored for each record. Source = Synthetic means the file was generated for this educational app and was not imported from a real operational system.",
                        className="model-note",
                        style={"marginTop": "12px"},
                    ),
                ],
                className="panel",
                style={"marginBottom": "16px"},
            ),
            html.Div(
                [
                    html.Div([html.H3("Scenario audit log"), html.P("Model baseline remains separate from human changes")], className="panel-header"),
                    data_table(
                        "audit-table",
                        _audit_records(),
                        columns=[
                            {"name": "Timestamp", "id": "timestamp"},
                            {"name": "Scenario", "id": "scenario"},
                            {"name": "Variable", "id": "variable"},
                            {"name": "Old value", "id": "old_value"},
                            {"name": "New value", "id": "new_value"},
                            {"name": "User", "id": "user"},
                            {"name": "Rationale", "id": "rationale"},
                        ],
                        page_size=8,
                    ),
                    html.Div(
                        "Each entry answers who changed which scenario variable, from what value to what new value, when, and why. Keeping this separate from the baseline makes scenario decisions reviewable and reversible.",
                        className="model-note",
                        style={"marginTop": "12px"},
                    ),
                ],
                className="panel",
                style={"marginBottom": "16px"},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H3("Known limitations"), html.P("What this prototype deliberately simplifies")], className="panel-header"),
                            html.Ul(
                                [
                                    html.Li("All company, customer, employee, invoice, and financial records are synthetic."),
                                    html.Li("Accounting and tax treatment are simplified and not jurisdictional advice."),
                                    html.Li("Monte Carlo results depend on selected distributions, bounds, and correlations."),
                                    html.Li("Statistical association and feature importance do not prove causality."),
                                    html.Li("Historical operating relationships may not persist through structural change."),
                                    html.Li("Compensation analysis is illustrative planning support, not a salary determination."),
                                    html.Li("Scenarios support decisions but do not replace management judgment."),
                                ],
                                style={"margin": "0", "paddingLeft": "18px", "color": "#657278", "fontSize": "11px", "lineHeight": "1.8"},
                            ),
                        ],
                        className="panel",
                    ),
                    html.Div(
                        [
                            html.Div([html.H3("Future roadmap"), html.P("Deliberately outside the MVP")], className="panel-header"),
                            html.Div(
                                [
                                    html.Div([html.Div("Phase 2", className="comparison-label"), html.Div("ERP and invoice integrations · authentication · scenario persistence", className="comparison-delta")], className="comparison-item"),
                                    html.Div([html.Div("Phase 3", className="comparison-label"), html.Div("Payment prediction · probabilistic forecasting · external signals", className="comparison-delta")], className="comparison-item"),
                                    html.Div([html.Div("Phase 4", className="comparison-label"), html.Div("Production API · planning integrations · automated variance explanations", className="comparison-delta")], className="comparison-item"),
                                ],
                                className="comparison-strip",
                                style={"gridTemplateColumns": "1fr"},
                            ),
                        ],
                        className="panel",
                    ),
                ],
                className="content-grid equal",
            ),
            html.Div(
                "NovaPlan is an educational proof-of-concept built using entirely synthetic data. It is not an official Deloitte product, does not represent Deloitte proprietary methodologies, and should not be used as financial, tax, accounting, or investment advice.",
                className="disclaimer",
            ),
        ]
    )


@callback(
    Output("audit-table", "data"),
    Input("global-audit-version", "data"),
)
def refresh_audit_table(_: int):
    return _audit_records()
