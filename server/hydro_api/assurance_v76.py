"""V7.6: conservative synthetic hydrology/engineering and cash-flow assurance.

No connection to Kolymaskaya / Ust-Srednekanskaya, real Magadan networks,
SCADA, corporate budgets or regulatory consent. Never an operating recommendation.
"""
from __future__ import annotations
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP
from math import exp, isfinite
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .studies import Strict, ForecastCase, CascadeCase
from .coupling_v75 import advance
from .programme_v74 import CapitalScreen, screen_capital


def as_money(v: Decimal) -> str:
    return str(v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class RoutingSpecification(Strict):
    """One linear routing tank: dS/dt=Qin-Qout, S=tau*Qout.

    This is an illustrative conservation model, NOT validated flood routing.
    """
    time_constant_hours: float = Field(gt=0.01, le=168)
    initial_routed_outflow_cms: float = Field(ge=0, le=100000)
    max_time_steps: int = Field(ge=3, le=72, default=72)
    mapping_ref: str = Field(min_length=20, max_length=140, pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')

    @field_validator('time_constant_hours', 'initial_routed_outflow_cms', 'max_time_steps', mode='before')
    @classmethod
    def no_bool(cls, v):
        if isinstance(v, bool):
            raise ValueError('BOOLEAN_NOT_ROUTING_PARAMETER')
        return v


def route_single_step(inflow_cms: float, old_outflow_cms: float, dt_seconds: float, tau_seconds: float) -> dict:
    """Exact mean discharge and end storage of one constant-inflow linear tank."""
    if any(not isfinite(v) for v in (inflow_cms, old_outflow_cms, dt_seconds, tau_seconds)):
        raise ValueError('NONFINITE_ROUTING_VALUE')
    if min(inflow_cms, old_outflow_cms) < 0 or min(dt_seconds, tau_seconds) <= 0:
        raise ValueError('INVALID_ROUTING_BOUNDARY')
    decay = exp(-dt_seconds / tau_seconds)
    end_discharge = inflow_cms + (old_outflow_cms - inflow_cms) * decay
    mean_discharge = inflow_cms + (old_outflow_cms - inflow_cms) * (tau_seconds / dt_seconds) * (1 - decay)
    start_storage = old_outflow_cms * tau_seconds
    end_storage = end_discharge * tau_seconds
    balance_residual = (start_storage + (inflow_cms - mean_discharge) * dt_seconds) - end_storage
    if abs(balance_residual) > 1e-7 * max(1.0, start_storage, end_storage):
        raise ArithmeticError('ROUTING_WATER_BALANCE_FAILED')
    return {'mean_arrival_cms':mean_discharge, 'end_arrival_cms':end_discharge,
            'start_routing_storage_m3':start_storage, 'end_routing_storage_m3':end_storage,
            'water_balance_residual_m3':balance_residual}


def routed_ensemble(forecast: ForecastCase, template: CascadeCase, routing: RoutingSpecification) -> dict:
    if template.upper.name == template.lower.name:
        raise ValueError('CASCADE_RESERVOIR_NAMES_NOT_DISTINCT')
    if len(forecast.targets) > routing.max_time_steps:
        raise ValueError('ROUTING_STEP_BUDGET_EXCEEDED')
    if not (1 <= template.period_hours <= 168):
        raise ValueError('ROUTING_HOURS_INCOMPATIBLE')
    dt = template.period_hours * 3600.0
    tau = routing.time_constant_hours * 3600.0
    targets = sorted(forecast.targets, key=lambda a: a.target_at.astimezone(timezone.utc))
    for i,t in enumerate(targets):
        if t.target_at <= forecast.issued_at:
            raise ValueError('FUTURE_TARGET_REQUIRED')
        if i and abs((t.target_at-targets[i-1].target_at).total_seconds() - dt) > 0.001:
            raise ValueError('ROUTING_REQUIRES_CONTIGUOUS_FORECAST')
    scenarios = {}
    for scenario in ('lower', 'point', 'upper'):
        u_store = template.upper.initial_storage_m3
        d_store = template.lower.initial_storage_m3
        prev_arrival = routing.initial_routed_outflow_cms
        rows, violations = [], []
        for i, target in enumerate(targets):
            predicted = {'lower':target.lower_cms,'point':target.predicted_cms,'upper':target.upper_cms}[scenario]
            # Forecast is additive only to the *synthetic upstream local inflow*.
            upper = advance(template.upper, u_store, predicted + template.upper.local_inflow_cms, template.period_hours)
            routed = route_single_step(upper['outflow_cms'], prev_arrival, dt, tau)
            down_inflow = template.lower.local_inflow_cms + routed['mean_arrival_cms']
            lower = advance(template.lower, d_store, down_inflow, template.period_hours)
            violations.extend(f'{scenario}:t{i}:{name}:{error}' for name,result in (('upper',upper),('lower',lower)) for error in result['constraints_breached'])
            rows.append({'time_utc':target.target_at.astimezone(timezone.utc).isoformat(),
                         'forecast_cms':predicted, 'upper':upper, 'lower':lower,
                         'routing':{key:round(val,9) for key,val in routed.items()}})
            prev_arrival = routed['end_arrival_cms']
            u_store, d_store = upper['final_storage_m3'], lower['final_storage_m3']
        scenarios[scenario] = {'violations':violations, 'step_count':len(rows),
                               'end_upper_storage_m3':round(u_store,3),
                               'end_lower_storage_m3':round(d_store,3),
                               'total_energy_mwh':round(sum(x['upper']['energy_mwh']+x['lower']['energy_mwh'] for x in rows),6),
                               'rows':rows}
    return {'status':'SYNTHETIC_BOUNDARY_BREACH' if any(s['violations'] for s in scenarios.values()) else 'SYNTHETIC_MASS_BALANCE_OK',
            'route':'LINEAR_RESERVOIR_EXACT_DISCHARGE', 'source':'HISTORICAL_PREDICTIONS_NOT_FUTURE_ACTUALS',
            'forecast_issued_at_utc':forecast.issued_at.astimezone(timezone.utc).isoformat(),
            'mapping_ref':routing.mapping_ref, 'scenario_envelope_kind':'UNCALIBRATED_INTERVAL_NOT_PROBABILITIES',
            'scenarios':scenarios, 'limitations':["Constant turbine releases, head and efficiency: energy cannot be optimised from this model",
             "Linear-reservoir routing is NOT site-calibrated hydraulic routing",
             "No legally required water-use rules, ecology, dispatch, reservoir curves or real Magadan measurements"],
            'independent_engineering_accepted':False,'industrial_approval_eligible':False}


class ValueBand(Strict):
    low: Decimal = Field(ge=0,le=Decimal('3'))
    base: Decimal = Field(ge=0,le=Decimal('3'))
    high: Decimal = Field(ge=0,le=Decimal('3'))

    @field_validator('low','base','high',mode='before')
    @classmethod
    def numeric_only(cls,v):
        if isinstance(v,bool): raise ValueError('BOOLEAN_NOT_VALUE_MULTIPLIER')
        return v

    @model_validator(mode='after')
    def sorted_bands(self):
        if not self.low<=self.base<=self.high:
            raise ValueError('VALUE_SCENARIOS_NOT_SORTED')
        return self


class AnnualValueModel(Strict):
    """Explicit synthetic revenue assumption; no hydro/diagnostic output is monetised automatically."""
    scope: Literal['SYNTHETIC_INCREMENTAL_CASHFLOWS_ONLY']='SYNTHETIC_INCREMENTAL_CASHFLOWS_ONLY'
    benefit_key: str = Field(min_length=5,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')
    source_assumption_ref: str = Field(min_length=20,max_length=140,pattern=r'^SYNTHETIC-[A-Za-z0-9_-]+$')
    discounted_from_year: int = Field(ge=2026,le=2045)
    discount_rate: Decimal = Field(ge=Decimal('0'),le=Decimal('0.6'))
    benefit_scenarios: ValueBand
    annual_gross_value_rub: dict[int,Decimal] = Field(min_length=1,max_length=20)
    annual_incremental_opex_rub: dict[int,Decimal] = Field(min_length=1,max_length=20)
    rationale: str = Field(min_length=40,max_length=1400)

    @field_validator('discount_rate','discounted_from_year',mode='before')
    @classmethod
    def reject_bool(cls,v):
        if isinstance(v,bool):raise ValueError('BOOLEAN_NOT_FINANCIAL_PARAMETER')
        return v

    @field_validator('annual_gross_value_rub','annual_incremental_opex_rub',mode='before')
    @classmethod
    def mapping_only(cls,v):
        if not isinstance(v,dict):return v
        if any(isinstance(k,bool) or isinstance(val,bool) for k,val in v.items()):
            raise ValueError('BOOLEAN_NOT_FINANCIAL_VALUE')
        return v

    @model_validator(mode='after')
    def years(self):
        years=set(self.annual_gross_value_rub)|set(self.annual_incremental_opex_rub)
        if set(self.annual_gross_value_rub)!=set(self.annual_incremental_opex_rub):
            raise ValueError('BENEFIT_AND_OPEX_YEARS_MISMATCH')
        if any(y<self.discounted_from_year or y>2045 for y in years):
            raise ValueError('BENEFIT_YEAR_OUTSIDE_HORIZON')
        if any(not x.is_finite() or x<0 or x>Decimal('1e15') for x in self.annual_gross_value_rub.values()):
            raise ValueError('INVALID_YEARLY_GROSS_VALUE')
        if any(not x.is_finite() or abs(x)>Decimal('1e15') for x in self.annual_incremental_opex_rub.values()):
            raise ValueError('INVALID_YEARLY_OPEX')
        return self


def discounted_value_model(finance:AnnualValueModel,capex:CapitalScreen) -> dict:
    """Single CAPEX source = WBS; no double-counting finance grants or loan principal."""
    cap_result=screen_capital(capex)
    principal={str(y):Decimal(row['with_contingency_rub']) for y,row in cap_result['cash_schedule'].items()}
    years=sorted(set(map(int,principal))|set(finance.annual_gross_value_rub))
    if any(y<finance.discounted_from_year for y in years):
        raise ValueError('CAPEX_BEFORE_DISCOUNT_ANCHOR')
    cashflows={}
    valuations={}
    for name in ('low','base','high'):
        factor=getattr(finance.benefit_scenarios,name)
        npv=Decimal('0');rows=[]
        for y in years:
            gross=finance.annual_gross_value_rub.get(y,Decimal('0'))*factor
            opex=finance.annual_incremental_opex_rub.get(y,Decimal('0'))
            cost=principal.get(str(y),Decimal('0'))
            net=gross-opex-cost
            discounted=net/(Decimal('1')+finance.discount_rate)**(y-finance.discounted_from_year)
            npv+=discounted
            rows.append({'year':y,'assumed_gross_value_rub':as_money(gross),'incremental_opex_rub':as_money(opex),
                         'wbs_capex_rub':as_money(cost),'net_cashflow_rub':as_money(net),'discounted_rub':as_money(discounted)})
        cashflows[name]=rows
        valuations[name]={'npv_rub':as_money(npv),'positive_npv':npv>0}
    return {'status':'LAB_CONSTRUCTION_CAP_BREACH' if cap_result['status']=='ASSUMED_BUDGET_CAP_BREACHED' else 'LAB_ANNUAL_CASHFLOW_CALCULATED',
            'scenario_results':valuations,'year_by_year':cashflows,'baseline_year':finance.discounted_from_year,
            'capital_screen':cap_result,'benefit_key':finance.benefit_key,'benefit_assumption_ref':finance.source_assumption_ref,
            'proof_status':'SYNTHETIC_ASSUMPTIONS_NOT_ATTESTED',
            'limitations':['WBS is the ONLY capital outflow; finance proceeds and grants are not counted as profit',
                           'No tariffs, VAT, taxes, inflation, real construction quantities or regulatory acceptance',
                           'Financial scenarios do not determine project obligation, feasibility, causality or legality'],
            'industrial_approval_eligible':False}
