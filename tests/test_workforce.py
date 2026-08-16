"""Workforce cost, ramp, and hiring-timing invariants."""

from __future__ import annotations

import pytest

from models.workforce import HireProposal, evaluate_hire, simulate_hiring_plan


def test_higher_salary_reduces_hire_ebitda_and_cash() -> None:
    lower = evaluate_hire(proposed_base_salary_eur=40_000)
    higher = evaluate_hire(proposed_base_salary_eur=48_000)

    assert higher["expected_billable_revenue_eur"] == pytest.approx(
        lower["expected_billable_revenue_eur"]
    )
    assert higher["ebitda_effect_eur"] < lower["ebitda_effect_eur"]
    assert higher["cash_effect_12m_eur"] < lower["cash_effect_12m_eur"]
    assert higher["break_even_utilization"] > lower["break_even_utilization"]


def test_equipment_capex_reduces_cash_but_not_ebitda() -> None:
    no_equipment = evaluate_hire(equipment_cost_eur=0)
    with_equipment = evaluate_hire(equipment_cost_eur=5_000)

    assert with_equipment["ebitda_effect_eur"] == pytest.approx(
        no_equipment["ebitda_effect_eur"]
    )
    assert with_equipment["cash_effect_12m_eur"] == pytest.approx(
        no_equipment["cash_effect_12m_eur"] - 5_000
    )


def test_hiring_plan_has_upfront_cost_and_gradual_productivity_ramp() -> None:
    plan = simulate_hiring_plan(
        hires=12,
        months=12,
        assumptions={"joining_months": 3, "ramp_up_months": 3},
    )

    joining_period = plan.loc[plan["new_hires"] > 0]
    assert len(joining_period) == 3
    assert (joining_period["recruiting_cost_eur"] > 0).all()
    assert (joining_period["onboarding_capex_eur"] > 0).all()
    assert plan.loc[0, "ramped_billable_fte"] < plan.loc[0, "incremental_headcount"]
    assert plan.loc[0, "incremental_cash_effect_eur"] < 0
    assert plan.loc[5, "incremental_revenue_eur"] > plan.loc[0, "incremental_revenue_eur"]
    assert plan.loc[5, "incremental_ebitda_eur"] > plan.loc[0, "incremental_ebitda_eur"]


def test_invalid_hire_assumptions_are_rejected() -> None:
    with pytest.raises(ValueError):
        HireProposal(expected_utilization=1.2)
