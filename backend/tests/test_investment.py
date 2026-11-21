from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.investment import FinancialAssumptions, appraise_investment


def assumptions(**overrides):
    return FinancialAssumptions.model_validate({
        "annual_savings_eur": 9_000,
        "annual_maintenance_eur": 2_000,
        "horizon_years": 20,
        "discount_rate_pct": 3,
    } | overrides)


def test_athens_example_cumulative_payback_and_sensitivity():
    result = appraise_investment(Decimal("96796.60"), assumptions())
    assert result.npv_eur == 7345.72
    assert result.cumulative_net_eur == 43203.40
    assert result.simple_payback_year == 14
    assert result.discounted_payback_year == 19
    assert result.required_annual_savings_eur == 8506.25
    assert [row.change_pct for row in result.sensitivity] == [-20, 0, 20]
    assert result.sensitivity[0].npv_eur < 0 < result.sensitivity[2].npv_eur
    assert result.sensitivity[1].npv_eur == result.npv_eur


def test_grant_reduces_municipal_outlay_with_delayed_savings():
    result = appraise_investment(Decimal(30_000), assumptions(
        grant_eur=10_000, annual_savings_eur=8000, annual_maintenance_eur=1000,
        horizon_years=5, discount_rate_pct=0, savings_delay_years=2,
    ))
    assert result.capital_cost_eur == 30_000 and result.net_initial_cost_eur == 20_000
    assert result.npv_eur == result.cumulative_net_eur == -1000
    assert result.simple_payback_year is None and result.discounted_payback_year is None
    assert result.required_annual_savings_eur == 8333.33


def test_full_grant_and_excluded_savings():
    result = appraise_investment(Decimal(3000), assumptions(grant_eur=3000, discount_rate_pct=0))
    assert result.simple_payback_year == result.discounted_payback_year == 0
    delayed = appraise_investment(Decimal(3000), assumptions(savings_delay_years=20))
    assert delayed.required_annual_savings_eur is None
    assert delayed.discounted_payback_year is None


def test_unsupported_assumptions_are_rejected():
    with pytest.raises(ValidationError):
        assumptions(horizon_years=5, savings_delay_years=6)
    with pytest.raises(ValidationError):
        assumptions(annual_maintenance_eur=-1)
    with pytest.raises(ValueError, match="επιχορήγηση"):
        appraise_investment(Decimal(4000), assumptions(grant_eur=4000.01))
