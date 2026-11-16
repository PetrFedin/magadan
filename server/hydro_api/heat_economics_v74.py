"""Synthetic heat-network comparison. Not a thermal-network solver or tariff model."""
from __future__ import annotations
from decimal import Decimal
from typing import Literal
from pydantic import Field, field_validator
from .studies import Strict, HeatCase
from .finance_evidence import PriceBand

class HeatMoney(Strict):
    scope: Literal['SYNTHETIC_HEAT_NOT_TARIFF']='SYNTHETIC_HEAT_NOT_TARIFF'
    hours_per_year: Decimal = Field(gt=0,le=Decimal('8784'))
    value_rub_per_kwh: PriceBand
    capital_cost_rub: Decimal = Field(ge=0,le=Decimal('1e15'))
    annual_opex_delta_rub: Decimal = Field(ge=Decimal('-1e15'),le=Decimal('1e15'))
    discount_rate: Decimal = Field(ge=0,le=Decimal('0.6'))
    years: int = Field(ge=1,le=30)
    notes: str = Field(min_length=20,max_length=1200)

    @field_validator('hours_per_year','capital_cost_rub','annual_opex_delta_rub','discount_rate','years',mode='before')
    @classmethod
    def reject_boolean(cls,x):
        if isinstance(x,bool):raise ValueError('BOOLEAN_NOT_A_FINANCIAL_INPUT')
        return x


def compare_heat(baseline:HeatCase,proposed:HeatCase,br:dict,pr:dict,finance:HeatMoney)->dict:
    invariants=('mass_flow_kg_s','supply_temp_c','return_temp_c','ambient_temp_c','cp_j_kg_k','length_m')
    differences=[field for field in invariants if getattr(baseline,field)!=getattr(proposed,field)]
    if differences:raise ValueError('UNMATCHED_HEAT_ENGINEERING_BASELINE:'+','.join(differences))
    if baseline.overall_u_w_m_k==proposed.overall_u_w_m_k:
        raise ValueError('NO_HEAT_ENGINEERING_ALTERNATIVE')
    # Flow temperatures are held constant. Upstream required heat changes only in
    # this deliberately simple steady-state lumped synthetic model.
    before=Decimal(str(br['estimated_pipe_loss_mw']))
    after=Decimal(str(pr['estimated_pipe_loss_mw']))
    delta_mwh=(before-after)*finance.hours_per_year
    delta_kwh=delta_mwh*Decimal('1000')
    annuity=sum((Decimal('1')+finance.discount_rate)**(-t) for t in range(1,finance.years+1))
    prices={}
    for name in ('low','base','high'):
        price=getattr(finance.value_rub_per_kwh,name)
        gross=delta_kwh*price
        net=gross-finance.annual_opex_delta_rub
        npv=-finance.capital_cost_rub+net*annuity
        prices[name]={'assumed_value_rub_per_kwh':str(price),'gross_annual_rub':str(round(gross,2)),
                      'net_annual_rub':str(round(net,2)),'npv_rub':str(round(npv,2))}
    return {'physical_assumption':'STEADY_STATE_IDENTICAL_LOADS_AND_TEMPERATURES_U_ONLY',
            'baseline_loss_mw':str(before),'proposed_loss_mw':str(after),
            'annual_synthetic_savings_kwh':str(round(delta_kwh,6)),
            'modelled_hours_per_year':str(finance.hours_per_year),
            'capital_cost_rub':str(finance.capital_cost_rub),
            'prices':prices,'field_ready':False,'industrial_finance_eligible':False,
            'limitations':['No heat tariff, climate normalisation, hydraulic calibration, seasonality, leak investigation or independent engineer signoff',
                          'No actual M&V baseline, taxes, funding, price escalation, grant or construction estimate']}
