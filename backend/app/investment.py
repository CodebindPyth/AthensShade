from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Budget, Cost, InterventionType, OptimizeRequest


class FinancialAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    annual_savings_eur: Budget
    annual_maintenance_eur: Budget
    horizon_years: Annotated[int, Field(strict=True, ge=1, le=40)]
    discount_rate_pct: Annotated[Decimal, Field(ge=0, le=30, decimal_places=2)]
    savings_delay_years: Annotated[int, Field(strict=True, ge=0, le=40)] = 0
    grant_eur: Budget = Decimal(0)
    capital_override_eur: Cost | None = None

    @model_validator(mode="after")
    def verify_delay(self) -> "FinancialAssumptions":
        if self.savings_delay_years > self.horizon_years:
            raise ValueError("Savings delay must be within the appraisal horizon")
        return self


class AppraiseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: OptimizeRequest
    assumptions: FinancialAssumptions
    intervention_type: InterventionType | None = None


class SensitivityResult(BaseModel):
    change_pct: int
    annual_savings_eur: float
    npv_eur: float


class FinancialAppraisal(BaseModel):
    capital_cost_eur: float
    net_initial_cost_eur: float
    npv_eur: float
    cumulative_net_eur: float
    simple_payback_year: int | None
    discounted_payback_year: int | None
    required_annual_savings_eur: float | None
    sensitivity: list[SensitivityResult]


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def appraise_investment(capital_cost: Decimal, assumptions: FinancialAssumptions) -> FinancialAppraisal:
    if assumptions.capital_override_eur is not None:
        capital_cost = assumptions.capital_override_eur
    if assumptions.grant_eur > capital_cost:
        raise ValueError("Η επιχορήγηση υπερβαίνει το κόστος του πλάνου.")

    own_outlay = capital_cost - assumptions.grant_eur
    maintenance = assumptions.annual_maintenance_eur
    savings = assumptions.annual_savings_eur
    discount_base = 1 + assumptions.discount_rate_pct / 100
    discount_factors = [discount_base ** -year for year in range(1, assumptions.horizon_years + 1)]
    savings_factor = sum(discount_factors[assumptions.savings_delay_years:], start=Decimal(0))
    maintenance_pv = maintenance * sum(discount_factors)

    cumulative = discounted = -own_outlay
    no_deficit = own_outlay == 0 and (
        maintenance == 0 or (assumptions.savings_delay_years == 0 and savings >= maintenance)
    )
    simple_payback = discounted_payback = 0 if no_deficit else None
    for year, factor in enumerate(discount_factors, start=1):
        flow = (savings if year > assumptions.savings_delay_years else 0) - maintenance
        cumulative += flow
        discounted += flow * factor
        if simple_payback is None and cumulative >= 0:
            simple_payback = year
        if discounted_payback is None and discounted >= 0:
            discounted_payback = year

    def present_value(gross: Decimal) -> Decimal:
        return gross * savings_factor - own_outlay - maintenance_pv

    sensitivity = []
    for change in (-20, 0, 20):
        gross = savings * (100 + change) / 100
        sensitivity.append(SensitivityResult(change_pct=change, annual_savings_eur=money(gross),
                                             npv_eur=money(present_value(gross))))

    return FinancialAppraisal(
        capital_cost_eur=money(capital_cost),
        net_initial_cost_eur=money(own_outlay),
        npv_eur=money(present_value(savings)),
        cumulative_net_eur=money(cumulative),
        simple_payback_year=simple_payback,
        discounted_payback_year=discounted_payback,
        required_annual_savings_eur=money((own_outlay + maintenance_pv) / savings_factor) if savings_factor else None,
        sensitivity=sensitivity,
    )
