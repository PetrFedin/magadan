"""HydroKontur V7.2: transparent synthetic studies for six product lanes.

None of these calculations is a field-validated engineering model. The grid
study invokes the previously checked two-bus solver. Results are explicitly
excluded from approval/production workflows.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from itertools import combinations
from math import sqrt
from statistics import median
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .engineering import GridCase, balanced_two_bus

MODULES = ('hydroforecast','cascade','turbine','gridloss','heatnet','hydrocapex')
ENGINE_VERSION = 'hk72-laboratory-models-1'

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class ForecastObservation(Strict):
    observed_at: datetime
    available_at: datetime
    flow_cms: float = Field(ge=0, le=100000)

class ForecastTarget(Strict):
    target_at: datetime
    truth_available_at: datetime
    actual_cms: float = Field(ge=0, le=100000)
    predicted_cms: float = Field(ge=0, le=100000)
    lower_cms: float = Field(ge=0, le=100000)
    upper_cms: float = Field(ge=0, le=100000)

class ForecastCase(Strict):
    issued_at: datetime
    training: list[ForecastObservation] = Field(min_length=3, max_length=1000)
    targets: list[ForecastTarget] = Field(min_length=3, max_length=500)
    @model_validator(mode='after')
    def timeline(self):
        for ts in [self.issued_at]+[z.observed_at for z in self.training]+[z.available_at for z in self.training]+[z.target_at for z in self.targets]+[z.truth_available_at for z in self.targets]:
            if ts.tzinfo is None or ts.utcoffset() is None:
                raise ValueError('Timezone-aware timestamps are required')
        if len({p.observed_at for p in self.training}) != len(self.training):
            raise ValueError('Duplicate training observation times')
        if len({p.target_at for p in self.targets}) != len(self.targets):
            raise ValueError('Duplicate forecast targets')
        if any(p.observed_at>self.issued_at or p.available_at>self.issued_at or p.available_at<p.observed_at for p in self.training):
            raise ValueError('FUTURE_INFORMATION_LEAKAGE_IN_TRAINING')
        if any(p.target_at<=self.issued_at or p.truth_available_at<p.target_at for p in self.targets):
            raise ValueError('Invalid historical forecast evaluation timeline')
        if any(p.lower_cms>p.predicted_cms or p.predicted_cms>p.upper_cms for p in self.targets):
            raise ValueError('Forecast intervals must enclose point prediction')
        return self

def forecast_quality(c: ForecastCase):
    errors=[p.predicted_cms-p.actual_cms for p in c.targets]
    n=len(errors)
    coverage=sum(p.lower_cms<=p.actual_cms<=p.upper_cms for p in c.targets)/n
    denominator=sum(p.actual_cms for p in c.targets)
    return {'evaluation_kind':'HINDCAST_ONLY','n_targets':n,'mae_cms':round(sum(abs(e) for e in errors)/n,6),
            'rmse_cms':round(sqrt(sum(e*e for e in errors)/n),6),
            'bias_cms':round(sum(errors)/n,6),
            'wape_percent':round(100*sum(abs(e) for e in errors)/denominator,6) if denominator else None,
            'interval_coverage_fraction':round(coverage,6),
            'limitations':'Historical error scoring only; no live forecast generation, no probability calibration proof'}

class ReservoirStep(Strict):
    name: str = Field(min_length=2, max_length=100)
    initial_storage_m3: float = Field(ge=0, le=1e13)
    min_storage_m3: float = Field(ge=0, le=1e13)
    max_storage_m3: float = Field(gt=0, le=1e13)
    local_inflow_cms: float = Field(ge=0, le=1e5)
    turbine_release_cms: float = Field(ge=0, le=1e5)
    spill_release_cms: float = Field(ge=0, le=1e5)
    other_losses_cms: float = Field(ge=0, le=1e5)
    min_total_release_cms: float = Field(ge=0, le=1e5)
    head_m: float = Field(gt=0, le=2000)
    efficiency: float = Field(gt=0, le=1)
    rated_capacity_mw: float = Field(gt=0, le=100000)
    @model_validator(mode='after')
    def limits(self):
        if self.min_storage_m3>self.max_storage_m3:raise ValueError('Reservoir volume bounds reversed')
        return self

class CascadeCase(Strict):
    period_hours: float = Field(gt=0, le=8784)
    upper: ReservoirStep
    lower: ReservoirStep
    assumption: Literal['instantaneous_upstream_release_no_travel_time']='instantaneous_upstream_release_no_travel_time'

def cascade_balance(c: CascadeCase):
    def step(s, upstream):
        incoming=s.local_inflow_cms+upstream
        release=s.turbine_release_cms+s.spill_release_cms
        volume=s.initial_storage_m3+(incoming-release-s.other_losses_cms)*c.period_hours*3600
        p=0.00981*s.turbine_release_cms*s.head_m*s.efficiency
        problems=[]
        if s.initial_storage_m3<s.min_storage_m3 or s.initial_storage_m3>s.max_storage_m3:problems.append('initial_storage_out_of_range')
        if volume<s.min_storage_m3-1e-6 or volume>s.max_storage_m3+1e-6:problems.append('final_storage_out_of_range')
        if release<s.min_total_release_cms:problems.append('minimum_release_not_met')
        if p>s.rated_capacity_mw+1e-9:problems.append('nameplate_capacity_exceeded')
        return {'reservoir':s.name,'final_storage_m3':round(volume,3),'power_mw':round(p,6),
                'energy_mwh':round(p*c.period_hours,6),'release_cms':release,'violations':problems}
    u=step(c.upper,0)
    d=step(c.lower,u['release_cms'])
    violations=[f"{z['reservoir']}:{p}" for z in (u,d) for p in z['violations']]
    return {'status':'INFEASIBLE' if violations else 'FEASIBLE_IN_SYNTHETIC_MODEL',
            'upper':u,'lower':d,'total_energy_mwh':round(u['energy_mwh']+d['energy_mwh'],6),
            'violations':violations,
            'limitations':'Single time step; no transit delay, routing, operating regulations, ramping, turbine curves or ecological field validation'}

class TurbineSample(Strict):
    observed_at: datetime
    load_mw: float = Field(ge=0,le=10000)
    vibration_mm_s: float = Field(ge=0,le=10000)

class TurbineCase(Strict):
    reference_load_mw:float=Field(gt=0,le=10000)
    comparable_band_percent:float=Field(gt=0,le=100)
    baseline:list[TurbineSample]=Field(min_length=6,max_length=300)
    recent:list[TurbineSample]=Field(min_length=3,max_length=100)
    @model_validator(mode='after')
    def valid_series(self):
        combined=self.baseline+self.recent
        if any(p.observed_at.tzinfo is None or p.observed_at.utcoffset() is None for p in combined):
            raise ValueError('Timezone-aware observation times required')
        if len({p.observed_at for p in combined})!=len(combined):raise ValueError('Duplicate observation timestamps')
        if max(p.observed_at for p in self.baseline)>=min(p.observed_at for p in self.recent):
            raise ValueError('Baseline and monitoring windows overlap')
        band=self.reference_load_mw*self.comparable_band_percent/100
        if any(abs(p.load_mw-self.reference_load_mw)>band for p in combined):
            raise ValueError('INCOMPARABLE_OPERATING_LOAD')
        return self

def turbine_deviation(c:TurbineCase):
    baseline=[p.vibration_mm_s for p in c.baseline]
    recent=[p.vibration_mm_s for p in c.recent]
    m=median(baseline)
    mad=median(abs(z-m) for z in baseline)
    robust_sigma=1.4826*mad
    if robust_sigma<=1e-12:
        return {'status':'INSUFFICIENT_VARIABILITY_FOR_SCORE','failure_probability':None,
                'baseline_median_mm_s':m,'recent_median_mm_s':median(recent),
                'limitations':'Cannot infer risk from a constant baseline; instrument and expert review required'}
    z=(median(recent)-m)/robust_sigma
    return {'status':'CHECK_SIGNAL' if z>=3.5 else 'NO_LAB_THRESHOLD_BREACH',
            'robust_z':round(z,6),'baseline_median_mm_s':m,
            'recent_median_mm_s':median(recent),'failure_probability':None,
            'limitations':'Laboratory MAD threshold is not an industrial alarm or probability of failure'}

class HeatCase(Strict):
    mass_flow_kg_s: float = Field(gt=0, le=1e6)
    supply_temp_c: float = Field(ge=-30,le=350)
    return_temp_c: float = Field(ge=-40,le=330)
    ambient_temp_c: float = Field(ge=-80,le=100)
    cp_j_kg_k: float = Field(ge=3500,le=5000)
    length_m: float = Field(gt=0,le=1e6)
    overall_u_w_m_k: float = Field(ge=0,le=10000)
    @model_validator(mode='after')
    def temperatures(self):
        if not (self.supply_temp_c>self.return_temp_c>self.ambient_temp_c):
            raise ValueError('Laboratory heat case needs supply > return > ambient')
        return self

def heat_balance(c:HeatCase):
    delivered=c.mass_flow_kg_s*c.cp_j_kg_k*(c.supply_temp_c-c.return_temp_c)/1e6
    loss=c.overall_u_w_m_k*c.length_m*((c.supply_temp_c+c.return_temp_c)/2-c.ambient_temp_c)/1e6
    return {'delivered_heat_mw':round(delivered,6),'estimated_pipe_loss_mw':round(loss,6),
            'estimated_upstream_supply_mw':round(delivered+loss,6),
            'limitations':'Lumped steady-state approximation; no pressure solving, axial cooling, network topology or calibrated physical asset model'}

Money=Decimal
class PortfolioProject(Strict):
    project_id:str=Field(min_length=2,max_length=70,pattern=r'^[a-zA-Z0-9_-]+$')
    benefit_key:str=Field(min_length=2,max_length=70,pattern=r'^[a-zA-Z0-9_-]+$')
    mandatory:bool=False
    depends_on:list[str]=Field(default_factory=list,max_length=15)
    exclusive_group:str|None=None
    costs_by_year_rub:list[Money]=Field(min_length=2,max_length=11)
    net_benefits_by_year_rub:list[Money]=Field(min_length=1,max_length=10)

class PortfolioCase(Strict):
    discount_rate:Money=Field(ge=Decimal('0'),le=Decimal('0.6'))
    annual_budgets_rub:list[Money]=Field(min_length=2,max_length=11)
    projects:list[PortfolioProject]=Field(min_length=1,max_length=12)
    @model_validator(mode='after')
    def structural(self):
        T=len(self.annual_budgets_rub)-1
        ids=[p.project_id for p in self.projects]
        if len(ids)!=len(set(ids)) or len({p.benefit_key for p in self.projects})!=len(ids):
            raise ValueError('DUPLICATE_PROJECT_OR_BENEFIT_KEY')
        lookup=set(ids)
        if any(len(p.costs_by_year_rub)!=T+1 or len(p.net_benefits_by_year_rub)!=T for p in self.projects):
            raise ValueError('CASHFLOW_HORIZON_MISMATCH')
        if any(x<0 for x in self.annual_budgets_rub) or any(x<0 for p in self.projects for x in p.costs_by_year_rub):
            raise ValueError('Negative budgets or costs not allowed')
        maximum=Decimal('1000000000000000')
        all_money=list(self.annual_budgets_rub)+[z for p in self.projects for z in p.costs_by_year_rub+p.net_benefits_by_year_rub]
        if any((not z.is_finite()) or abs(z)>maximum for z in all_money):
            raise ValueError('INVALID_OR_OUT_OF_RANGE_MONEY')
        if any(p.project_id in p.depends_on or any(d not in lookup for d in p.depends_on) for p in self.projects):
            raise ValueError('INVALID_PROJECT_DEPENDENCY')
        graph={p.project_id:p.depends_on for p in self.projects}
        visiting=set(); visited=set()
        def visit(k):
            if k in visiting:raise ValueError('CYCLIC_DEPENDENCY')
            if k in visited:return
            visiting.add(k)
            for z in graph[k]:visit(z)
            visiting.remove(k);visited.add(k)
        for i in ids:visit(i)
        return self

def capex_portfolio(c:PortfolioCase):
    projects=c.projects; T=len(c.annual_budgets_rub)-1
    npv={}
    for p in projects:
        value=-p.costs_by_year_rub[0]
        for y in range(1,T+1):
            value+=(p.net_benefits_by_year_rub[y-1]-p.costs_by_year_rub[y])/(Decimal('1')+c.discount_rate)**y
        npv[p.project_id]=value
    mandatory={p.project_id for p in projects if p.mandatory}
    winner=None
    for bits in range(1<<len(projects)):
        chosen={p.project_id for i,p in enumerate(projects) if bits&(1<<i)}
        if not mandatory.issubset(chosen):continue
        if any(not set(p.depends_on).issubset(chosen) for p in projects if p.project_id in chosen):continue
        groups=[p.exclusive_group for p in projects if p.project_id in chosen and p.exclusive_group]
        if len(groups)!=len(set(groups)):continue
        costs=[sum((p.costs_by_year_rub[y] for p in projects if p.project_id in chosen),Decimal('0')) for y in range(T+1)]
        if any(costs[y]>c.annual_budgets_rub[y] for y in range(T+1)):continue
        value=sum((npv[k] for k in chosen),Decimal('0'))
        score=(value,-len(chosen),tuple(sorted(chosen)))
        if winner is None or score>winner[0]:winner=(score,chosen,costs)
    if winner is None:
        return {'status':'NO_FEASIBLE_PORTFOLIO','selected':[],
                'npv_rub':None,'reason':'Mandatory projects, dependencies, exclusivity or budgets conflict',
                'limitations':'Lab sample, not authorization to reject mandatory safety works'}
    _,chosen,costs=winner
    return {'status':'FEASIBLE_SYNTHETIC_PORTFOLIO',
            'selected':sorted(chosen),'excluded':sorted(p.project_id for p in projects if p.project_id not in chosen),
            'selected_npv_rub':str(round(sum((npv[k] for k in chosen),Decimal('0')),2)),
            'used_budget_by_year_rub':[str(x) for x in costs],
            'individual_npv_rub':{k:str(round(v,2)) for k,v in npv.items()},
            'limitations':'Brute-force constrained portfolio for <=12 synthetic projects; no construction permits, tariff model or regulated capex validation'}

SCHEMA={
    'hydroforecast':ForecastCase,
    'cascade':CascadeCase,
    'turbine':TurbineCase,
    'gridloss':GridCase,
    'heatnet':HeatCase,
    'hydrocapex':PortfolioCase,
}

def compute_study(module:str,case:dict)->dict:
    if module not in SCHEMA:raise ValueError('UNSUPPORTED_MODULE')
    if module=='gridloss' and case.get('model_kind')=='radial_ac_v73':
        from .radial_grid import RadialCase,solve_radial
        validated=RadialCase.model_validate(case)
        return {'module':module,'model_version':'hk73-balanced-radial-synthetic-v1',
                'result':solve_radial(validated),
                'assurance':{'dataset':'SYNTHETIC_LAB', 'independent_field_verification':False,
                             'industrial_decision_eligible':False,'scada_access':False}}
    c=SCHEMA[module].model_validate(case)
    if module=='hydroforecast':r=forecast_quality(c)
    elif module=='cascade':r=cascade_balance(c)
    elif module=='turbine':r=turbine_deviation(c)
    elif module=='gridloss':r=balanced_two_bus(c)
    elif module=='heatnet':r=heat_balance(c)
    else:r=capex_portfolio(c)
    return {'module':module,'model_version':ENGINE_VERSION,'result':r,
            'assurance':{'dataset':'SYNTHETIC_LAB','independent_field_verification':False,
                         'industrial_decision_eligible':False,'scada_access':False}}
