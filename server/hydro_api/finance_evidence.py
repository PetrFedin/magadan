"""V7.3 synthetic physical-to-money reconciliation, NOT tariff / grant / site economics."""
from __future__ import annotations
from decimal import Decimal, getcontext
from typing import Literal
from pydantic import Field, model_validator, field_validator
from .radial_grid import Strict, RadialCase, physical_comparability

getcontext().prec = 36

class PriceBand(Strict):
    low: Decimal = Field(ge=Decimal('0'), le=Decimal('10000'))
    base: Decimal = Field(ge=Decimal('0'), le=Decimal('10000'))
    high: Decimal = Field(ge=Decimal('0'), le=Decimal('10000'))

    @field_validator('low','base','high',mode='before')
    @classmethod
    def forbid_bool_prices(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_A_PRICE')
        return v
    @model_validator(mode='after')
    def order(self):
        if any(not x.is_finite() for x in (self.low,self.base,self.high)):
            raise ValueError('NON_FINITE_UNIT_PRICE')
        if not self.low<=self.base<=self.high:
            raise ValueError('UNORDERED_PRICE_SCENARIOS')
        return self

class LabFinance(Strict):
    scope: Literal['SYNTHETIC_NOT_A_TARIFF'] = 'SYNTHETIC_NOT_A_TARIFF'
    capital_cost_rub: Decimal = Field(ge=Decimal('0'),le=Decimal('1000000000000000'))
    annual_opex_delta_rub: Decimal = Field(ge=Decimal('-1000000000000000'),le=Decimal('1000000000000000'))
    value_per_kwh_rub: PriceBand
    discount_rate: Decimal = Field(ge=Decimal('0'),le=Decimal('0.6'))
    years: int = Field(ge=1, le=30)
    annual_repeat_count: Decimal = Field(gt=Decimal('0'), le=Decimal('8784'))
    notes: str = Field(min_length=18,max_length=1200)

    @field_validator('capital_cost_rub','annual_opex_delta_rub','discount_rate','annual_repeat_count','years',mode='before')
    @classmethod
    def forbid_bool_finance(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_IS_NOT_A_FINANCIAL_PARAMETER')
        return v
    @model_validator(mode='after')
    def finite(self):
        if not all(v.is_finite() for v in (self.capital_cost_rub,self.annual_opex_delta_rub,
                                          self.discount_rate,self.annual_repeat_count)):
            raise ValueError('NON_FINITE_FINANCIAL_INPUT')
        return self


def evaluate_feeder_alternative(baseline_case:RadialCase, proposed_case:RadialCase,
                                baseline_result:dict,proposed_result:dict,parameters:LabFinance)->dict:
    comparable, reasons=physical_comparability(baseline_case,proposed_case)
    if not comparable:
        raise ValueError('PHYSICAL_BASELINE_MISMATCH:'+','.join(reasons))
    if proposed_result.get('constraint_violations'):
        raise ValueError('PROPOSED_SCENARIO_HAS_ENGINEERING_LIMIT_BREACH')
    if baseline_result.get('industrial_decision_eligible') is not False or proposed_result.get('industrial_decision_eligible') is not False:
        raise ValueError('ASSURANCE_PERIMETER_MISMATCH')
    hours=Decimal(str(baseline_result['modelled_hours'])) * parameters.annual_repeat_count
    if hours>Decimal('8784.000001'):
        raise ValueError('ASSUMED_YEAR_EXCEEDS_8784_HOURS')
    # Losses are MWh. Convert with x1000 to kWh before multiplying by RUB/kWh.
    window_mwh=Decimal(str(baseline_result['total_line_energy_loss_mwh']))-Decimal(str(proposed_result['total_line_energy_loss_mwh']))
    savings_kwh=window_mwh*Decimal('1000')*parameters.annual_repeat_count
    annuity=sum((Decimal('1')+parameters.discount_rate)**(-t) for t in range(1,parameters.years+1))
    output={}
    for label in ('low','base','high'):
        unit_value=getattr(parameters.value_per_kwh_rub,label)
        gross=savings_kwh*unit_value
        net=gross-parameters.annual_opex_delta_rub
        npv=-parameters.capital_cost_rub+net*annuity
        output[label]={
            'unit_value_rub_per_kwh':str(unit_value),
            'gross_annual_value_rub':str(round(gross,2)),
            'net_annual_value_rub':str(round(net,2)),
            'npv_rub':str(round(npv,2)),
        }
    threshold=None
    if savings_kwh>0 and annuity>0:
        threshold=(parameters.capital_cost_rub/annuity+parameters.annual_opex_delta_rub)/savings_kwh
    return {
        'comparison_status':'MATCHED_SYNTHETIC_INVARIANTS_NOT_CAUSAL_EVIDENCE',
        'assurance_status':'RESEARCH_ONLY_NO_INDUSTRIAL_SIGNOFF',
        'baseline_loss_mwh':str(baseline_result['total_line_energy_loss_mwh']),
        'proposed_loss_mwh':str(proposed_result['total_line_energy_loss_mwh']),
        'window_savings_mwh':str(round(window_mwh,9)),
        'modelled_window_hours':str(baseline_result['modelled_hours']),
        'annual_repeat_count':str(parameters.annual_repeat_count),
        'assumed_annual_hours':str(hours),
        'annual_energy_savings_kwh':str(round(savings_kwh,6)),
        'construction_cost_rub':str(parameters.capital_cost_rub),
        'annual_opex_delta_rub':str(parameters.annual_opex_delta_rub),
        'discount_rate':str(parameters.discount_rate),
        'years':parameters.years,
        'annuity_factor':str(round(annuity,12)),
        'price_scenarios':output,
        'break_even_unit_value_rub_per_kwh':str(round(threshold,5)) if threshold is not None else None,
        'baseline_has_constraint_violations':bool(baseline_result.get('constraint_violations')),
        'limitations':('Assumed constant annual net benefit for all years, synthetic network, '
                       'no actual tariff, taxes, replacement life, depreciation, degradation, '
                       'M&V, grant, construction estimate or engineering approval. '
                       'Counterfactual benefits remain unproven.'),
        'industrial_investment_eligible':False,
    }
