"""NovaPlan analytical core.

All model functions operate independently from Dash so they can be tested,
reused in exports, or exposed through a future API.
"""

from .cashflow import build_13_week_forecast, build_liquidity_forecast
from .driver_tree import RevenueDrivers, driver_tree_from_mapping, revenue_driver_tree
from .forecast import ForecastAssumptions, build_monthly_forecast, rolling_forecast
from .insights import generate_insights
from .monte_carlo import run_monte_carlo
from .revenue import build_revenue_schedule, calculate_revenue, revenue_from_drivers
from .scenarios import (
    SCENARIO_LIBRARY,
    compare_scenarios,
    expansion_decision_cases,
    run_scenario,
    scenario_assumptions,
    summarize_forecast,
)
from .sensitivity import run_sensitivity, tornado_summary
from .statements import (
    assert_reconciled,
    build_statements,
    check_reconciliation,
    reconciliation_checks,
)
from .workforce import (
    HireProposal,
    compensation_band,
    evaluate_hire,
    proposed_hire_economics,
    simulate_hiring_plan,
    workforce_rollforward,
)
from .working_capital import (
    WorkingCapitalAssumptions,
    build_working_capital,
    calculate_ap,
    calculate_ar,
    calculate_collections,
    forecast_invoice_collections,
    invoice_aging,
)

__all__ = [
    "ForecastAssumptions",
    "HireProposal",
    "RevenueDrivers",
    "SCENARIO_LIBRARY",
    "WorkingCapitalAssumptions",
    "assert_reconciled",
    "build_13_week_forecast",
    "build_liquidity_forecast",
    "build_monthly_forecast",
    "build_revenue_schedule",
    "build_statements",
    "build_working_capital",
    "calculate_ap",
    "calculate_ar",
    "calculate_collections",
    "calculate_revenue",
    "check_reconciliation",
    "compare_scenarios",
    "compensation_band",
    "driver_tree_from_mapping",
    "evaluate_hire",
    "expansion_decision_cases",
    "forecast_invoice_collections",
    "generate_insights",
    "invoice_aging",
    "proposed_hire_economics",
    "reconciliation_checks",
    "revenue_driver_tree",
    "revenue_from_drivers",
    "rolling_forecast",
    "run_monte_carlo",
    "run_scenario",
    "run_sensitivity",
    "scenario_assumptions",
    "simulate_hiring_plan",
    "summarize_forecast",
    "tornado_summary",
    "workforce_rollforward",
]
